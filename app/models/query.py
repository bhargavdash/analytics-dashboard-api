# QueryRequest , QueryResponse - Pydantic models for API request and response validation

from pydantic import BaseModel

class QueryRequest(BaseModel):
    question: str
    # Present on follow-up questions — ties the new turn to an existing conversation
    # and lets the orchestrator load prior turns as context. Absent = start fresh.
    conversation_id: str | None = None

class QueryResponse(BaseModel):
    query_id: str
    question: str
    status: str
