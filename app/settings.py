import os
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "lm-studio")

LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
ROUTING_BASE_URL = os.getenv("ROUTING_BASE_URL", "https://router.project-osrm.org")
ROUTING_PROFILE = os.getenv("ROUTING_PROFILE", "driving")
