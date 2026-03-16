from openai import OpenAI

from app.settings import API_BASE_URL, API_KEY, EMBEDDING_MODEL

client = OpenAI(
    base_url=API_BASE_URL,
    api_key=API_KEY,
)


def _embed(text: str) -> list[float]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Texto vacio para embedding")

    resp = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return resp.data[0].embedding


def embed_query(text: str) -> list[float]:
    # E5 retrieval works best when search queries use the "query:" prefix.
    return _embed(f"query: {text}")


def embed_passage(text: str) -> list[float]:
    # Stored KB cases should be embedded as passages/documents.
    return _embed(f"passage: {text}")
