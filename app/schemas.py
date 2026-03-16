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


class BinnibusStop(BaseModel):
    stop_order: int
    stop_name: str
    latitude: float
    longitude: float
    description: Optional[str] = None


class BinnibusRoute(BaseModel):
    route_code: str
    route_name: str
    display_name: str
    origin: str
    destination: str
    description: Optional[str] = None
    stops: list[BinnibusStop]
    path: list[list[float]] = []
