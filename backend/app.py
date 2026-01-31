import sys
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Fix for Windows + Python 3.8+ asyncio event loop issues
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- IMPORTS FROM YOUR PROJECT ---
from backend.scrapers.rss_scraper import ingest_from_feeds
from backend.elasticsearch.es_client import get_es
from backend.config import INDEX_NAME
from backend.agent import CrisisAgent  # <--- NEW: Import the Agent
from backend.models.user_model import User
from fastapi import HTTPException
# --- BACKGROUND TASK LOGIC ---
async def run_agent_lifecycle():
    """
    Runs the Scraper and Crisis Agent in a background loop forever.
    This replaces the need for a separate 'run_live_system.py' script.
    """
    print(" SYSTEM STARTUP: Background Agent Service Initiated")
    agent = CrisisAgent()

    while True:
        try:
            print("\n [Background] Starting Scheduled Patrol...")
            
            # 1. Run Scraper (in a thread to avoid blocking the API)
            # We limit to 5 articles per feed to keep the background cycle fast
            print("   > Fetching fresh news...")
            await asyncio.to_thread(ingest_from_feeds, limit_per_feed=5)
            
            # 2. Run Agent Patrol
            print("   > Agent analyzing risks...")
            await asyncio.to_thread(agent.run_patrol)
            
            print(" [Background] Cycle complete. Sleeping for 10 minutes...")
        except Exception as e:
            print(f" [Background] Error: {e}")
        
        # Sleep for 600 seconds (10 minutes)
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan Manager.
    Starts the background task when the API starts, and cleans up when it stops.
    """
    # STARTUP: Create the background task
    asyncio.create_task(run_agent_lifecycle())
    yield
    # SHUTDOWN: (Optional cleanup code goes here)
    print(" SYSTEM SHUTDOWN: Agent stopping...")

# --- APP DEFINITION ---
app = FastAPI(title="News Analyser API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API ENDPOINTS ---
USERS_INDEX = "news_users"

@app.post("/auth/login")
def login_user(user_data: User):
    """
    Simple Hackathon Login: 
    If email exists, return profile. If not, create new user.
    """
    es = get_es()
    email = user_data.email.lower().strip()
    
    # Check if user exists
    if not es.indices.exists(index=USERS_INDEX):
        es.indices.create(index=USERS_INDEX)
        
    try:
        # Search for user by email
        res = es.search(index=USERS_INDEX, body={
            "query": {"term": {"email.keyword": email}}
        })
        
        if res['hits']['total']['value'] > 0:
            # User found! Return their data
            user_doc = res['hits']['hits'][0]['_source']
            return {"status": "success", "user": user_doc, "new": False}
        else:
            # New User! Create them
            new_user = {"email": email, "watchlist": []}
            es.index(index=USERS_INDEX, body=new_user)
            # Refresh so it's available immediately
            es.indices.refresh(index=USERS_INDEX) 
            return {"status": "success", "user": new_user, "new": True}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/user/watchlist")
def update_watchlist(user_data: User):
    """Updates the topics a user wants to watch."""
    es = get_es()
    email = user_data.email.lower().strip()
    
    # Find the user's document ID first
    res = es.search(index=USERS_INDEX, body={
        "query": {"term": {"email.keyword": email}}
    })
    
    if res['hits']['total']['value'] == 0:
        raise HTTPException(status_code=404, detail="User not found")
        
    doc_id = res['hits']['hits'][0]['_id']
    
    # Update the watchlist
    es.update(index=USERS_INDEX, id=doc_id, body={
        "doc": {"watchlist": user_data.watchlist}
    })
    
    return {"status": "updated", "watchlist": user_data.watchlist}
@app.get("/debug/mapping")
def get_mapping():
    """Debug endpoint to check Elasticsearch mapping"""
    es = get_es()
    try:
        mapping = es.indices.get_mapping(index=INDEX_NAME)
        return mapping
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug/sample")
def get_sample_doc():
    """Debug endpoint to get a raw sample document"""
    es = get_es()
    try:
        res = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1)
        if res["hits"]["hits"]:
            return {
                "raw_document": res["hits"]["hits"][0],
                "_source_keys": list(res["hits"]["hits"][0]["_source"].keys())
            }
        return {"message": "No documents found"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/ingest/run")
def run_ingest(limit_per_feed: int = 20):
    """Manual trigger to run the scraper immediately"""
    try:
        print(f"DEBUG - Starting ingestion with limit_per_feed={limit_per_feed}")
        result = ingest_from_feeds(limit_per_feed=limit_per_feed)
        print(f"DEBUG - Ingestion result: {result}")
        return result
    except Exception as e:
        import traceback
        print(f"DEBUG - Ingestion error: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/articles/search")
def search_articles(
    q: Optional[str] = Query(None, description="query string"),
    language: Optional[str] = None,
    sentiment: Optional[str] = None,
    bias: Optional[str] = None,
    size: int = 20
):
    print(f"DEBUG - Search request: q={q}, language={language}, sentiment={sentiment}, bias={bias}, size={size}")
    
    es = get_es()
    
    # Check if index exists
    if not es.indices.exists(index=INDEX_NAME):
        print(f"DEBUG - Index {INDEX_NAME} does not exist!")
        return {"count": 0, "results": []}
    
    must = []
    if q:
        must.append({"multi_match": {"query": q, "fields": ["title^2", "original_text", "summary"]}})
    if language:
        must.append({"term": {"language": language}})
    if sentiment:
        must.append({"term": {"sentiment_overall": sentiment}})
    if bias:
        must.append({"term": {"bias_overall": bias}})

    # 1. Define the query logic
    query_logic = {"bool": {"must": must}} if must else {"match_all": {}}

    # 2. Build the full body WITH sorting (Newest First)
    body = {
        "query": query_logic,
        "sort": [
            { "published_date": { "order": "desc" } }
        ]
    }
    
    print(f"DEBUG - Elasticsearch query: {body}")
    
    try:
        res = es.search(index=INDEX_NAME, body=body, size=size)
        
        # ... (Existing Debug Logic Omitted for Brevity, but safe to keep) ...
    
        hits = []
        for h in res["hits"]["hits"]:
            source = h["_source"]
            article = {
                "id": h["_id"],
                "score": h["_score"],
                "title": source.get("title"),
                "url": source.get("url"),
                "source_name": source.get("source_name"),
                "published_date": source.get("published_date"),
                "language": source.get("language"),
                "original_text": source.get("original_text"),
                "translated_text": source.get("translated_text"),
                "summary": source.get("summary"),
                "sentiment_overall": source.get("sentiment_overall"),
                "sentiment_score": source.get("sentiment_score"),
                "bias_overall": source.get("bias_overall"),
                "bias_score": source.get("bias_score"),
                "entities": source.get("entities", []),
                "scraped_at": source.get("scraped_at"),
                "tags": source.get("tags", [])
            }
            hits.append(article)
    
        return {"count": len(hits), "results": hits}
        
    except Exception as e:
        print(f"DEBUG - Search error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"count": 0, "results": [], "error": str(e)}