from pydantic import BaseModel
from typing import Optional

class SearchRequest(BaseModel):
    text: str
    top_k: int = 3

class SearchResult(BaseModel):
    found: bool
    case_id: Optional[int] = None
    solution_text: Optional[str] = None
    similarity: Optional[float] = None

class CreateCaseRequest(BaseModel):
    incident_text: str
    solution_text: str

class FeedbackRequest(BaseModel):
    case_id: int
    helpful: bool  