# POST API query - streaming response (SSE)

import json
import asyncio
from fastapi import APIRouter 
from fastapi.responses import StreamingResponse
from app.models.query import QueryRequest

router = APIRouter()

async def fake_stream(question: str):
    events = [
        ("reasoning", {"step": "parese", "message": f"Parsing: {question}"}),
        ("reasoning", {"step": "sql_gen", "message": "Generating SQL..."}),
        ("reasoning", {"step": "db_exec", "message": "Running query on DuckDB..."}),
        ("widget", {
            "type": "bar_chart",
            "title": "Revenue by Region (hardcoded)",
            "data": [
                {"region": "North", "revenue": 100000},
                {"region": "Europe", "revenue": 75000},
                {"region": "Asia", "revenue": 50000}
            ]
        }),
        ("done", {"message": "Query complete"})
    ]

    for event_type, payload in events:
        yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
        await asyncio.sleep(1)  # Simulate delay between events

@router.post("/query")
async def query_stream(request: QueryRequest):
    return StreamingResponse(
        fake_stream(request.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable buffering for nginx
        }
    )