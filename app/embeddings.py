import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

def embed(text: str) -> list[float]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Texto vacío para embedding")
    resp = client.embeddings.create(model=MODEL, input=text)
    return resp.data[0].embedding