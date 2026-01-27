from elasticsearch import Elasticsearch
from backend.config import ES_HOST
from backend.config import INDEX_NAME

def get_es():
    es = Elasticsearch(ES_HOST)
    if not es.ping():
        raise RuntimeError("Elasticsearch is not reachable at %s" % ES_HOST)
    return es

def get_latest_articles(limit=10):
    """
    Fetches the most recent articles from Elasticsearch.
    """
    es = get_es() # Connects using your code
    
    response = es.search(
        index="news_articles", # Make sure this matches your actual index name
        body={
            "query": {
                "match_all": {} # Gets everything (you can add filters here later)
            },
            "sort": [
                {
                    "published_date": {
                        "order": "desc" # THIS is the line that puts new articles first
                    }
                }
            ],
            "size": limit # How many articles to return (default 10)
        }
    )

    # Extract just the useful data (the '_source' part)
    articles = [hit['_source'] for hit in response['hits']['hits']]
    return articles