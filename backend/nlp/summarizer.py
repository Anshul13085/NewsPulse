from transformers import pipeline
from backend.config import SUMMARIZER_MODEL, MAX_SUMMARY_TOKENS
import logging
import torch

logger = logging.getLogger(__name__)

# --- GLOBAL MODEL LOADING (The Fix) ---
# We load the model ONCE here, at the top level.
# This prevents race conditions where multiple threads try to load it simultaneously.
try:
    # Check for GPU
    device = 0 if torch.cuda.is_available() else -1
    logger.info(f"Loading Summarizer on device: {device} (GPU={torch.cuda.is_available()})")
    
    # Load the pipeline globally immediately
    _summarizer_pipeline = pipeline(
        "summarization",
        model=SUMMARIZER_MODEL,
        device=device
    )
    logger.info(f"✅ Summarizer Model loaded globally: {SUMMARIZER_MODEL}")

except Exception as e:
    logger.error(f"❌ Failed to load global summarizer: {str(e)}")
    _summarizer_pipeline = None

def truncate_for_model(text: str, max_tokens: int = 900) -> str:
    """
    Truncate text to fit within model's maximum input length.
    Leaves some buffer for special tokens.
    """
    if not text:
        return text
    
    # Rough approximation: 1 token ≈ 4 characters for English
    max_chars = max_tokens * 4
    
    if len(text) <= max_chars:
        return text
    
    # Try to truncate at sentence boundaries
    truncated = text[:max_chars]
    
    # Find the last complete sentence
    last_period = truncated.rfind('.')
    last_exclamation = truncated.rfind('!')
    last_question = truncated.rfind('?')
    
    last_sentence_end = max(last_period, last_exclamation, last_question)
    
    # If we found a sentence boundary in the last 20% of the truncated text
    if last_sentence_end > max_chars * 0.8:
        return truncated[:last_sentence_end + 1].strip()
    
    # Otherwise, truncate at word boundary
    last_space = truncated.rfind(' ')
    if last_space > max_chars * 0.9:
        return truncated[:last_space].strip()
    
    # Last resort: hard truncate
    return truncated.strip()

def summarize(text: str, max_tokens: int = MAX_SUMMARY_TOKENS) -> str:
    """
    Summarize text using the globally loaded model.
    """
    try:
        if not text or not text.strip():
            return ""
        
        # Fallback if model failed to load
        if _summarizer_pipeline is None:
            logger.warning("Summarizer model not loaded, using fallback truncation.")
            return text[:300] + "..."

        # Check if text is too short to summarize
        word_count = len(text.split())
        if word_count < 40:
            return text
        
        # Truncate text to fit model constraints
        truncated_text = truncate_for_model(text, max_tokens=1024)
        
        # Dynamic length calculation
        # We want the summary to be roughly 1/3 of the input, but within bounds
        input_len = len(truncated_text.split())
        max_gen_len = min(max_tokens, 150) # Cap summary at 150 tokens
        min_gen_len = min(30, int(input_len * 0.2)) # At least 20% of input or 30 tokens

        # Ensure min < max
        if min_gen_len >= max_gen_len:
            min_gen_len = max(10, max_gen_len - 10)

        # Run Inference
        result = _summarizer_pipeline(
            truncated_text,
            max_length=max_gen_len,
            min_length=min_gen_len,
            do_sample=False,
            truncation=True
        )
        
        if result and len(result) > 0 and "summary_text" in result[0]:
            return result[0]["summary_text"].strip()
        else:
            return ""
            
    except Exception as e:
        logger.error(f"Summarization failed: {str(e)}")
        # Return first few sentences as fallback
        sentences = text.split('.')[:3]
        fallback = '. '.join(sentences).strip()
        if fallback and not fallback.endswith('.'):
            fallback += '.'
        return fallback

if __name__ == "__main__":
    # Simple test
    print(summarize("This is a test to see if the global model works correctly."))