from transformers import pipeline
import logging
import torch

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- GLOBAL MODEL LOADING (The Fix) ---
# We load the model ONCE here, at the top level.
_sentiment_classifier = None

try:
    device = 0 if torch.cuda.is_available() else -1
    logger.info(f"Loading Sentiment Model on device: {device} (GPU={torch.cuda.is_available()})")
    
    # Using a reliable sentiment model
    _sentiment_classifier = pipeline(
        "sentiment-analysis",
        model="cardiffnlp/twitter-roberta-base-sentiment-latest",
        framework="pt",
        device=device
    )
    logger.info("✅ Sentiment classifier loaded globally.")

except Exception as e:
    logger.error(f"❌ Failed to load global sentiment classifier: {str(e)}")
    # Fallback to default model if specific one fails
    try:
        _sentiment_classifier = pipeline(
            "sentiment-analysis",
            framework="pt",
            device=device
        )
        logger.info("✅ Loaded default sentiment classifier (Fallback).")
    except Exception as e2:
        logger.error(f"❌ Failed to load default sentiment classifier: {str(e2)}")
        _sentiment_classifier = None


def truncate_text(text: str, max_length: int = 400) -> str:
    """Truncate text for sentiment analysis"""
    if len(text) <= max_length * 4:  # rough char to token ratio
        return text
    
    truncated = text[:max_length * 4]
    last_space = truncated.rfind(' ')
    if last_space > len(truncated) * 0.8:
        return truncated[:last_space]
    return truncated

def classify_sentiment(text: str) -> tuple[str, float]:
    """
    Classify sentiment of text using the global classifier.
    Returns: (sentiment_label, confidence_score)
    """
    try:
        if not text or not text.strip():
            logger.warning("Empty text provided for sentiment analysis")
            return "neutral", 0.0
        
        if _sentiment_classifier is None:
            logger.warning("Sentiment classifier not loaded")
            return "neutral", 0.0
        
        # Truncate text to avoid sequence length issues
        truncated_text = truncate_text(text)
        # logger.info(f"Analyzing sentiment for text: {truncated_text[:100]}...")
        
        result = _sentiment_classifier(truncated_text, truncation=True, max_length=512)
        
        if result and len(result) > 0:
            label = result[0]['label'].lower()
            score = result[0]['score']
            
            # logger.info(f"Raw sentiment result: {result[0]}")
            
            # Normalize labels (different models use different formats)
            if label in ['positive', 'pos', 'label_2']:
                sentiment = 'positive'
            elif label in ['negative', 'neg', 'label_0']:
                sentiment = 'negative'
            else:
                sentiment = 'neutral'
            
            # logger.info(f"Sentiment classified: {sentiment} (score: {score:.3f})")
            return sentiment, float(score)
        
        logger.warning("No result from sentiment classifier")
        return "neutral", 0.0
        
    except Exception as e:
        logger.error(f"Sentiment classification failed: {str(e)}")
        return "neutral", 0.0

def test_sentiment():
    """Test sentiment analysis with various texts"""
    test_texts = [
        "This is absolutely wonderful news! I'm so happy about this development.",
        "This is terrible and disappointing. I hate when things go wrong.",
        "The weather is okay today. Nothing special happening.",
        "The government announced new policies that will impact the economy significantly."
    ]
    
    print("Testing Sentiment Analysis:")
    print("=" * 60)
    
    for i, text in enumerate(test_texts, 1):
        print(f"\nTest {i}: {text}")
        try:
            sentiment, score = classify_sentiment(text)
            print(f"Result: {sentiment.upper()} (confidence: {score:.3f})")
        except Exception as e:
            print(f"Error: {str(e)}")
    
    print("\n" + "=" * 60)
    print("Sentiment analysis test complete!")

if __name__ == "__main__":
    test_sentiment()