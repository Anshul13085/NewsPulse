import feedparser
from newspaper import Article, Config
from datetime import datetime
from typing import List, Dict, Optional
import hashlib
import concurrent.futures
from backend.nlp.language import detect_language
from backend.nlp.translator import translate_to_english
from backend.nlp.summarizer import summarize
from backend.nlp.sentiment import classify_sentiment
from backend.nlp.entities import extract_entities
from backend.nlp.bias import classify_bias
from backend.models.article_model import ArticleDoc, EntitySentiment
from backend.elasticsearch.es_client import get_es
from backend.config import INDEX_NAME
from elasticsearch.helpers import bulk
import trafilatura
import logging
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    logging.warning("BeautifulSoup not available, title extraction may be limited")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
RSS_FEEDS = [
    "https://feeds.feedburner.com/ndtvnews-top-stories",
    "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "https://www.thehindu.com/feeder/default.rss",
    "http://feeds.bbci.co.uk/news/rss.xml",
    "http://rss.cnn.com/rss/cnn_topstories.rss",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://techcrunch.com/feed/",
    "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "https://economictimes.indiatimes.com/rssfeeds/1977021501.cms",
    "https://www.livemint.com/rss/business",
    "https://www.livemint.com/rss/markets",
    "https://www.livemint.com/rss/money",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
    "https://www.wired.com/feed/rss",
    "https://www.wired.com/feed/category/science/rss",
    "https://www.theverge.com/rss/index.xml",
    "https://timesofindia.indiatimes.com/rssfeeds/66997905.cms",
    "https://feeds.feedburner.com/gadgets360-latest"
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# --- GLOBAL SESSION SETUP (Fixes Connection Pool Warning) ---
session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=20,  # Increase pool size
    pool_maxsize=20,      # Increase max size to handle parallel threads
    max_retries=Retry(total=3, backoff_factor=1)
)
session.mount("http://", adapter)
session.mount("https://", adapter)
session.headers.update({"User-Agent": USER_AGENT})


def generate_id(url: str) -> str:
    """Generates a unique ID for duplicate prevention."""
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def truncate_text(text: str, max_tokens: int = 800) -> str:
    if not text: return text
    max_chars = max_tokens * 4
    if len(text) <= max_chars: return text
    truncated = text[:max_chars]
    last_period = truncated.rfind('.')
    if last_period > max_chars * 0.8: return truncated[:last_period + 1]
    return truncated

def clean_title(title: str) -> str:
    if not title: return ""
    title = ' '.join(title.split())
    unwanted_patterns = [r'\s*-\s*[^-]*$', r'^\s*[|\-]\s*', r'\s*[|\-]\s*$']
    for pattern in unwanted_patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    if len(title) > 200:
        title = title[:200].rsplit(' ', 1)[0] + "..."
    return title.strip()

def is_valid_title(title: str) -> bool:
    if not title or len(title.strip()) < 10: return False
    title_lower = title.lower().strip()
    invalid_titles = ['untitled', 'no title', 'article', 'news', 'page not found', 'error', '404', 'access denied']
    if any(inv in title_lower for inv in invalid_titles): return False
    return True

def extract_title_from_url(url: str) -> str:
    try:
        clean_url = url.replace('https://', '').replace('http://', '').replace('www.', '')
        parts = clean_url.split('/')
        if len(parts) >= 2:
            meaningful_parts = [p for p in parts[1:] if len(p) > 4 and not any(x in p for x in ['index', 'html'])]
            if meaningful_parts:
                title_part = max(meaningful_parts, key=len)
                return ' '.join(word.capitalize() for word in title_part.replace('-', ' ').replace('_', ' ').split())
        return "News Article"
    except:
        return "News Article"

def fetch_feed_entries(limit_per_feed: int = 20) -> List[Dict]:
    items = []
    # Fetch feeds sequentially is fast enough (network headers only)
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:limit_per_feed]:
                items.append({
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link"),
                    "published": entry.get("published", None),
                    "source": feed.feed.get("title") or feed_url,
                    "description": entry.get("description", "")
                })
        except Exception as e:
            logger.error(f"Error fetching feed {feed_url}: {e}")
    return items

def extract_title_from_html(downloaded_html: str, url: str) -> Optional[str]:
    """Extract title from HTML using BeautifulSoup."""
    if not BeautifulSoup or not downloaded_html:
        return None
    try:
        soup = BeautifulSoup(downloaded_html, 'html.parser')
        title_selectors = [
            ('meta[property="og:title"]', 'content'), ('meta[name="twitter:title"]', 'content'),
            ('meta[property="twitter:title"]', 'content'), ('title', 'text'), ('h1', 'text'),
            ('.headline', 'text'), ('.title', 'text'), ('.article-title', 'text'),
            ('.post-title', 'text'), ('[class*="headline"]', 'text'), ('[class*="title"]', 'text'),
        ]
        for selector, attr_type in title_selectors:
            try:
                elements = soup.select(selector)
                for element in elements[:3]:
                    if attr_type == 'content': title = element.get('content', '').strip()
                    else: title = element.get_text(strip=True)
                    if title and is_valid_title(title): return clean_title(title)
            except: continue
        return None
    except Exception as e:
        # logger.error(f"HTML title extraction failed for {url}: {e}")
        return None

def extract_title_from_content(text: str) -> Optional[str]:
    if not text or len(text) < 50: return None
    sentences = re.split(r'[.!?]+', text)
    for sentence in sentences[:5]:
        sentence = sentence.strip()
        if (15 <= len(sentence) <= 150 and not sentence.lower().startswith(('the article', 'this article', 'according to', 'in a', 'on ', 'at '))):
            cleaned = clean_title(sentence)
            if is_valid_title(cleaned): return cleaned
    return None

def download_article(url: str) -> Optional[Dict]:
    # 1. Try Trafilatura with Custom Session (Fixes 403 & Connection Warnings)
    try:
        # Use our global session which has pool_maxsize set
        response = session.get(url, timeout=10)
        
        if response.status_code == 200:
            text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
            if text and len(text.strip()) > 100:
                title = None
                try:
                    meta = trafilatura.extract_metadata(response.text)
                    if meta and hasattr(meta, 'title') and meta.title:
                        pt = clean_title(meta.title)
                        if is_valid_title(pt): title = pt
                except: pass
                
                if not title: title = extract_title_from_html(response.text, url)
                if not title: title = extract_title_from_content(text)
                
                return {"title": title, "text": text, "method": "trafilatura", "publish_date": None}
    except Exception as e:
        # logger.warning(f"Trafilatura failed: {e}") 
        pass

    # 2. Fallback to Newspaper3k with Config
    try:
        config = Config()
        config.browser_user_agent = USER_AGENT
        config.request_timeout = 10

        art = Article(url, config=config, keep_article_html=False)
        art.download()
        art.parse()
        if art.text and len(art.text.strip()) > 100:
            title = None
            if art.title:
                pt = clean_title(art.title)
                if is_valid_title(pt): title = pt
            return {"title": title, "text": art.text, "authors": art.authors, "publish_date": art.publish_date, "top_image": art.top_image, "method": "newspaper3k"}
    except: pass
    
    return None

def iso_date(dt) -> Optional[str]:
    if isinstance(dt, datetime): return dt.isoformat()
    return None

def safe_nlp_operation(operation_name: str, operation_func, *args, **kwargs):
    try: return operation_func(*args, **kwargs)
    except Exception as e:
        logger.error(f"{operation_name} failed: {str(e)}")
        return None

def validate_and_create_entities(entities_data) -> List[EntitySentiment]:
    entities = []
    if not entities_data: return entities
    for e in entities_data:
        try:
            name = e.get("name")
            if name is None or not isinstance(name, str) or not name.strip(): continue
            entity = EntitySentiment(
                name=name.strip(), type=e.get("type", "misc"), sentiment=e.get("sentiment", "neutral"),
                bias=e.get("bias"), score=e.get("score")
            )
            entities.append(entity)
        except: continue
    return entities

def process_single_article(entry: Dict) -> Optional[Dict]:
    """
    Downloads and processes a SINGLE article. 
    Designed to run in a parallel thread.
    """
    url = entry['link']
    es = get_es()
    doc_id = generate_id(url)

    # 1. FAST CHECK: Does it exist?
    if es.exists(index=INDEX_NAME, id=doc_id):
        # logger.info(f"⏭️  Skipping existing: {url[:30]}...")
        return None # Return None to signal "skipped"

    # 2. SLOW PART: Download & NLP
    # If we are here, it's a NEW article.
    logger.info(f"⬇️  Downloading: {url[:30]}...")
    raw_article = download_article(url)
    
    if not raw_article:
        return None

    text = truncate_text(raw_article['text'])
    
    # Title Logic
    final_title = None
    # Priority 1: RSS feed title
    rss_title = entry.get('title', '').strip()
    if rss_title and is_valid_title(rss_title): final_title = clean_title(rss_title)
    # Priority 2: Extracted title
    if not final_title:
        extracted = raw_article.get('title')
        if extracted and is_valid_title(extracted): final_title = clean_title(extracted)
    # Priority 3: Content-based
    if not final_title:
        content_title = extract_title_from_content(text)
        if content_title and is_valid_title(content_title): final_title = content_title
    # Priority 4: URL-based
    if not final_title: final_title = extract_title_from_url(url)
    if not final_title or not is_valid_title(final_title):
        final_title = f"Article from {url.split('//')[1].split('/')[0] if '//' in url else 'Unknown Source'}"

    # NLP Pipeline
    lang = safe_nlp_operation("Language detection", detect_language, text) or "en"
    translated_text = None
    if lang != "en":
        translated_result = safe_nlp_operation("Translation", translate_to_english, text)
        if translated_result:
            text = translated_result
            translated_text = translated_result
    
    # We use safe defaults if NLP fails to save time
    summary = safe_nlp_operation("Summarization", summarize, text)
    entities_data = safe_nlp_operation("Entity extraction", extract_entities, text)
    entities = validate_and_create_entities(entities_data)

    bias_result = safe_nlp_operation("Bias classification", classify_bias, text)
    bias_overall, bias_score = ("neutral", 0.0)
    if bias_result and len(bias_result) >= 2:
        bias_overall = bias_result[0] or "neutral"
        bias_score = bias_result[1] or 0.0
    
    sentiment_result = safe_nlp_operation("Sentiment classification", classify_sentiment, text)
    sentiment_overall, sentiment_score = ("neutral", 0.0)
    if sentiment_result and len(sentiment_result) >= 2:
        sentiment_overall = sentiment_result[0] or "neutral"
        sentiment_score = sentiment_result[1] or 0.0

    # Format Date
    pub_date = raw_article.get('publish_date')
    if not pub_date and entry.get('published'):
        try:
            from dateutil import parser
            pub_date = parser.parse(entry['published'])
        except: pass
    
    pub_date_str = iso_date(pub_date)
    
    # Build the Pydantic Model first to ensure validation
    article_doc = ArticleDoc(
        title=final_title,
        url=url,
        source_name=entry['source'],
        published_date=pub_date_str,
        language=lang,
        original_text=raw_article['text'][:5000],
        translated_text=translated_text,
        summary=summary,
        bias_overall=bias_overall,
        bias_score=bias_score,
        sentiment_overall=sentiment_overall,
        sentiment_score=sentiment_score,
        entities=entities
    )

    # Return dict for Bulk Indexing
    doc_dict = article_doc.model_dump()
    doc_dict['url'] = str(doc_dict['url'])
    
    return {
        "_index": INDEX_NAME,
        "_id": doc_id,
        "_source": doc_dict
    }

def ingest_from_feeds(limit_per_feed: int = 20):
    """
    Parallelized Ingestion.
    """
    es = get_es()
    
    # 1. Fetch all links (Fast)
    feed_entries = fetch_feed_entries(limit_per_feed)
    logger.info(f"🌍 Found {len(feed_entries)} articles across all feeds. Starting parallel processing...")

    docs_to_index = []
    
    # 2. Parallel Process (The Speed Boost)
    # We use 5 workers. Going too high might crash your laptop if NLP models are heavy.
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks
        futures = [executor.submit(process_single_article, entry) for entry in feed_entries]
        
        # Collect results as they finish
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    docs_to_index.append(result)
                    logger.info(f"✅ Processed: {result['_source']['title'][:30]}...")
            except Exception as e:
                logger.error(f"❌ Worker Error: {e}")

    # 3. Bulk Index (Fast Database Insert)
    if docs_to_index:
        logger.info(f"💾 Bulk Indexing {len(docs_to_index)} new articles...")
        success, failed = bulk(es, docs_to_index, stats_only=True)
        logger.info(f"🎉 Indexed {success} articles successfully.")
    else:
        logger.info("💤 No new articles to index.")

    return {
        "total_fetched": len(feed_entries),
        "new_indexed": len(docs_to_index)
    }