import re
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from config import QdrantConfig
# symbol removal and text cleaning
def clean_text(text):
    text = re.sub(r'\x00', ' ', text)
    text = re.sub(r'[\u2500-\u27FF]', ' ', text)
    text = re.sub(r'[\u2000-\u206F]', ' ', text)
    text = re.sub(r'[^\x20-\x7E]', ' ', text)
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

# garbage detection after cleaning
def is_garbage_text(text):
    cleaned = re.sub(r'[^\x20-\x7E]', ' ', text)
    cleaned = re.sub(r' +', ' ', cleaned).strip()
    words   = cleaned.split()

    if len(words) < 10:                 
        return True

    avg_len = sum(len(w) for w in words) / len(words)
    if avg_len < 2.5:
        return True

    return False


def setup_qdrant():
    try:
        qdrant_config = QdrantConfig()
        client = QdrantClient(
            host=qdrant_config.host,
            port=qdrant_config.port
        )
        return client
    except Exception as e:
        print("Qdrant is not connected")
        print("First run: docker run -p 6333:6333 qdrant/qdrant")
        raise e

def load_model():
    model= SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return model

