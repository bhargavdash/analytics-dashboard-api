from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError
from app.models.widgets import DashboardSchema, DataRow
from app.services.a2ui_schema import generate_widgets, stream_insight

router = APIRouter()


class SchemaRequest(BaseModel):
    question: str
    rows: list[DataRow]


@router.post("/schema", response_model=DashboardSchema)
async def generate_schema(request: SchemaRequest):
    # Sprint-3 standalone endpoint: hand-fed rows → dashboard schema, no DB, no streaming.
    # The /query path streams the insight; here we just collect it into one string so the
    # non-streaming DashboardSchema contract is preserved.
    try:
        summary = "".join(
            [tok async for tok in stream_insight(request.question, request.rows)]
        ).strip()
        widgets = await generate_widgets(request.question, request.rows)
        return DashboardSchema(summary=summary, widgets=widgets)
    except ValidationError as e:
        # LLM returned JSON that failed Pydantic validation — surface the exact fields
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
