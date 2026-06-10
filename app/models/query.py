# QueryRequest , QueryResponse - Pydantic models for API request and response validation

from pydantic import BaseModel

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    query_id: str
    question: str
    status: str
