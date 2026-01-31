import time
from datetime import datetime, timedelta
from backend.elasticsearch.es_client import get_es
from backend.config import INDEX_NAME

class CrisisAgent:
    def __init__(self):
        self.es = get_es()

    def analyze_topic_risk(self, topic):
        # 1. Define 'Recent' (Last 24 hours)
        yesterday = (datetime.now() - timedelta(hours=24)).isoformat()

        # 2. Build the query
        query = {
            "bool": {
                "must": [
                    {"multi_match": {"query": topic, "fields": ["title", "summary"]}},
                    {"range": {"published_date": {"gte": yesterday}}}, 
                ],
                "filter": [
                    {"term": {"sentiment_overall": "negative"}} 
                ]
            }
        }

        # 3. Fetch Data
        response = self.es.search(
            index=INDEX_NAME,
            body={
                "query": query,
                "sort": [{"published_date": "desc"}],
                "size": 5,
                "_source": ["title", "url", "source_name", "published_date", "summary"]
            }
        )

        hits = response['hits']['hits']
        articles_data = [h['_source'] for h in hits]

        # Get summary from the first article
        top_summary = "No summary available."
        if articles_data and articles_data[0].get("summary"):
            top_summary = articles_data[0].get("summary")

        return {
            "topic": topic,
            "is_critical": len(hits) > 0,
            "article_count": len(hits),
            "articles_data": articles_data,
            "top_summary": top_summary
        }

    def run_patrol(self):
        print(f"  Agent starting PERSONALIZED patrol at {datetime.now().strftime('%H:%M:%S')}...")
        
        # 1. Fetch Users
        try:
            if not self.es.indices.exists(index="news_users"):
                print("    User index not found. Skipping.")
                return
            res = self.es.search(index="news_users", body={"query": {"match_all": {}}, "size": 1000})
            users = [hit['_source'] for hit in res['hits']['hits']]
        except Exception as e:
            print(f"    Error fetching users: {e}")
            return

        # 2. Map Topics
        topic_map = {} 
        for user in users:
            for topic in user.get('watchlist', []):
                clean_topic = topic.strip()
                if clean_topic not in topic_map:
                    topic_map[clean_topic] = []
                topic_map[clean_topic].append(user['email'])
        
        if not topic_map:
            print("    No topics in any watchlist.")
            return

        print(f"   > Monitoring {len(topic_map)} unique topics: {list(topic_map.keys())}")

        risk_list = [] 
        
        # 3. Analyze Risks
        for topic, emails in topic_map.items():
            print(f"    Checking topic: {topic}...", end="\r") # Progress update
            risk_data = self.analyze_topic_risk(topic)
            
            if risk_data['is_critical']:
                print(f"    CRITICAL MATCH: '{topic}' - Found {risk_data['article_count']} articles")
                
                # CRITICAL FIX: Map the summary to 'ai_assessment' key so reporter finds it
                risk_data['ai_assessment'] = risk_data['top_summary']
                risk_data['users_affected'] = emails
                
                risk_list.append(risk_data)
            else:
                pass # Silent for non-critical to keep logs clean

        # 4. Generate ONE Report
        if risk_list:
            self.generate_alert_batch(risk_list)
        else:
            print("    All clear. No risks detected.")

    def generate_alert_batch(self, risk_list):
        from backend.reporter import generate_html_report
        import webbrowser
        
        print(f"    Generating Briefing for {len(risk_list)} topics...")
        report_path = generate_html_report(risk_list)
        
        # Opens ONE tab
        webbrowser.open('file://' + report_path)