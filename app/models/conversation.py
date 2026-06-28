from pydantic import BaseModel
from app.models.widgets import Widget


class ConversationMeta(BaseModel):
    """Sidebar list item — no heavy payload, just enough to render the row."""
    id: str
    title: str
    dataset: str
    created_at: str
    updated_at: str
    turn_count: int
    widget_count: int | None = None


class ReasoningStep(BaseModel):
    tool: str
    title: str
    detail: str | None = None


class Turn(BaseModel):
    id: str
    seq: int
    question: str
    sql: str | None = None
    summary: str | None = None
    widgets: list[Widget] = []
    reasoningSteps: list[ReasoningStep] = []
    created_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    dataset: str
    dataset_id: str | None = None
    created_at: str
    updated_at: str
    turns: list[Turn] = []
