import os

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
INDEX_NAME = os.getenv("ES_INDEX", "news_articles")  # you already created this
DEFAULT_LANG = "en"

# Model names (change later if you want different ones)
SENTIMENT_MODEL = os.getenv("SENTIMENT_MODEL", "cardiffnlp/twitter-xlm-roberta-base-sentiment")
NER_MODEL = os.getenv("NER_MODEL", "Davlan/xlm-roberta-base-ner-hrl")
BIAS_MODEL = os.getenv("BIAS_MODEL", "joeddav/xlm-roberta-large-xnli")

# Summarizer: good English baseline; multilingual options are heavier/slow
SUMMARIZER_MODEL = os.getenv("SUMMARIZER_MODEL", "sshleifer/distilbart-cnn-12-6")
MAX_SUMMARY_TOKENS = int(os.getenv("MAX_SUMMARY_TOKENS", "160"))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"