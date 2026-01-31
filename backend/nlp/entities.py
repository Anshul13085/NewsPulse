import logging
from typing import List, Dict, Optional
import spacy
from transformers import pipeline
import torch

logger = logging.getLogger(__name__)

# --- GLOBAL MODEL LOADING (The Fix) ---
# We load models ONCE here, at the top level.
# This prevents race conditions where multiple threads try to load them simultaneously.

# 1. Load Spacy (Lightweight)
_nlp_spacy = None
try:
    _nlp_spacy = spacy.load("en_core_web_sm")
    logger.info("✅ Spacy model loaded globally.")
except OSError:
    logger.warning("⚠️ Spacy model not found. Will attempt fallback to Transformers.")
    _nlp_spacy = None

# 2. Load Transformers NER (Heavy - Needs Global Protection)
_ner_pipeline = None
try:
    device = 0 if torch.cuda.is_available() else -1
    logger.info(f"Loading NER Model on device: {device} (GPU={torch.cuda.is_available()})")
    
    _ner_pipeline = pipeline(
        "ner", 
        model="dbmdz/bert-large-cased-finetuned-conll03-english",
        aggregation_strategy="simple",
        device=device
    )
    logger.info("✅ Transformers NER Model loaded globally.")
except Exception as e:
    logger.error(f"❌ Failed to load Transformers NER model: {e}")
    _ner_pipeline = None


def extract_entities(text: str) -> List[Dict]:
    """
    Extract named entities from text with proper validation.
    Returns a list of dictionaries with entity information.
    """
    if not text or not isinstance(text, str):
        logger.warning("Invalid text provided for entity extraction")
        return []
    
    entities = []
    
    try:
        # Method 1: Try Spacy first (Faster)
        if _nlp_spacy:
            entities.extend(_extract_with_spacy(text))
        
        # Method 2: Fallback/Augment with Transformers (More Accurate)
        elif _ner_pipeline:
            entities.extend(_extract_with_transformers(text))
        
        else:
            logger.warning("No NER models available")
            return []
        
        # Filter and validate entities
        validated_entities = _validate_entities(entities)
        
        # logger.debug(f"Extracted {len(validated_entities)} valid entities")
        return validated_entities
        
    except Exception as e:
        logger.error(f"Entity extraction failed: {str(e)}")
        return []

def _extract_with_spacy(text: str) -> List[Dict]:
    """Extract entities using the global Spacy model"""
    entities = []
    if _nlp_spacy is None: return []

    try:
        doc = _nlp_spacy(text[:2000])  # Limit text length to avoid memory issues
        
        for ent in doc.ents:
            if ent.text and len(ent.text.strip()) > 1:  # Filter out single characters
                entities.append({
                    "name": ent.text.strip(),
                    "type": ent.label_.lower(),
                    "sentiment": "neutral",  # Default sentiment
                    "bias": None,
                    "score": 0.9,  # High confidence for Spacy
                    "start": ent.start_char,
                    "end": ent.end_char
                })
    except Exception as e:
        logger.error(f"Spacy entity extraction failed: {str(e)}")
    
    return entities

def _extract_with_transformers(text: str) -> List[Dict]:
    """Extract entities using the global Transformers pipeline"""
    entities = []
    if _ner_pipeline is None: return []

    try:
        # Limit text length to avoid memory issues (BERT limit is usually 512 tokens)
        truncated_text = text[:1000] 
        results = _ner_pipeline(truncated_text)
        
        for result in results:
            if result.get('word') and len(result['word'].strip()) > 1:
                entities.append({
                    "name": result['word'].strip(),
                    "type": result.get('entity_group', 'misc').lower(),
                    "sentiment": "neutral",
                    "bias": None,
                    "score": float(result.get('score', 0.5)),
                    "start": result.get('start'),
                    "end": result.get('end')
                })
    
    except Exception as e:
        logger.error(f"Transformers entity extraction failed: {str(e)}")
    
    return entities

def _validate_entities(entities: List[Dict]) -> List[Dict]:
    """
    Validate and clean entity data to prevent Pydantic validation errors
    """
    validated = []
    
    for entity in entities:
        try:
            # Ensure name is not None and is a valid string
            name = entity.get("name")
            if not name or not isinstance(name, str):
                continue
            
            # Clean the name
            name = name.strip()
            if not name or len(name) < 2:
                continue
            
            # Remove entities that are just punctuation or numbers
            if name.isdigit() or all(c in '.,!?;:()-[]{}"\'' for c in name):
                continue
            
            # Ensure other fields have valid values
            validated_entity = {
                "name": name,
                "type": str(entity.get("type", "misc")).lower(),
                "sentiment": str(entity.get("sentiment", "neutral")).lower(),
                "bias": entity.get("bias"),  # Can be None
                "score": float(entity.get("score", 0.5)) if entity.get("score") is not None else 0.5
            }
            
            # Additional validation for sentiment
            if validated_entity["sentiment"] not in ["positive", "negative", "neutral"]:
                validated_entity["sentiment"] = "neutral"
            
            validated.append(validated_entity)
            
        except Exception as e:
            continue
    
    # Remove duplicates based on name (case-insensitive)
    seen_names = set()
    unique_entities = []
    
    for entity in validated:
        name_lower = entity["name"].lower()
        if name_lower not in seen_names:
            seen_names.add(name_lower)
            unique_entities.append(entity)
    
    return unique_entities

# Test function
def test_entity_extraction():
    """Test the entity extraction with sample text"""
    sample_text = """
    President Joe Biden met with Prime Minister Narendra Modi in Washington D.C. 
    They discussed climate change and economic cooperation between the United States and India.
    Apple Inc. announced new products while Google continues to innovate in AI.
    """
    
    entities = extract_entities(sample_text)
    
    print(f"Extracted {len(entities)} entities:")
    for entity in entities:
        print(f"- {entity['name']} ({entity['type']})")

if __name__ == "__main__":
    test_entity_extraction()