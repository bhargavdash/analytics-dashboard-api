# POST API query - streaming response (SSE)

from fastapi import APIRouter 
from fastapi.responses import StreamingResponse
from app.models.query import QueryRequest
from app.services.orchestrator import run_query

router = APIRouter()

@router.post("/query")
async def query_stream(request: QueryRequest):
    return StreamingResponse(
        run_query(request.question, request.conversation_id, request.dataset_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable buffering for nginx
        }
    )