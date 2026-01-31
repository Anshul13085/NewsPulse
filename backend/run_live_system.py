import time
import schedule # You might need to pip install schedule
from backend.scrapers.rss_scraper import scrape_all_feeds # Import your actual scraper function
from backend.agent import CrisisAgent

def job():
    print("\n" + "="*50)
    print(f" SYSTEM SYNC STARTING: {time.strftime('%H:%M:%S')}")
    print("="*50)

    # 1. RUN SCRAPER (Fetch Real News)
    print(" Fetching latest news from RSS feeds...")
    try:
        # Assuming scrape_all_feeds() runs your scraper and returns how many new docs were added
        # If your function doesn't return a count, just run it.
        scrape_all_feeds() 
        print(" Scrape complete.")
    except Exception as e:
        print(f" Scraper Error: {e}")

    # 2. RUN AGENT (Analyze the new data)
    print("  Agent starting patrol...")
    try:
        agent = CrisisAgent()
        agent.run_patrol() # This triggers the HTML report if it finds risks
    except Exception as e:
        print(f" Agent Error: {e}")
        
    print(f" Sleeping until next cycle...")

# --- CONFIGURATION ---
# Run every 10 minutes (Real-time enough for news, but polite to the RSS servers)
schedule.every(10).minutes.do(job)

# Run once immediately on startup so you don't have to wait 10 mins
job()

while True:
    schedule.run_pending()
    time.sleep(1)