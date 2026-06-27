import json
import asyncio
from typing import AsyncIterator
from app.services.a2ui_schema import generate_dashboard_schema
from app.models.widgets import DataRow

SAMPLE_ROWS: list[DataRow] = [
    {"region": "North America", "revenue": 1200000, "orders": 4500},
    {"region": "Europe", "revenue": 950000, "orders": 3200},
    {"region": "Asia Pacific", "revenue": 780000, "orders": 2800},
    {"region": "Latin America", "revenue": 420000, "orders": 1600},
    {"region": "Middle East", "revenue": 310000, "orders": 1100},
]

def _emit(event_type: str, payload: dict) -> str: 
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


async def run_query(question: str) -> AsyncIterator[str]:
    yield _emit("reasoning", {"step": "parse", "message": f"Understanding: {question}"})
    await asyncio.sleep(0.3)

    yield _emit("reasoning", {"step": "db_exec", "message": "Using hand-fed sample rows (Sprint 3)"})
    await asyncio.sleep(0.3)

    yield _emit("reasoning", {"step": "a2ui_schema", "message": "Asking LLM to generate dashboard schema..."})

    schema = await generate_dashboard_schema(question, SAMPLE_ROWS)

    yield _emit("dashboard", schema.model_dump())
    yield _emit("done", {"message": "Complete"})