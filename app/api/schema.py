from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError
from app.models.widgets import DashboardSchema, DataRow
from app.services.a2ui_schema import generate_dashboard_schema

router = APIRouter()


class SchemaRequest(BaseModel):
    question: str
    rows: list[DataRow]


@router.post("/schema", response_model=DashboardSchema)
async def generate_schema(request: SchemaRequest):
    try:
        return await generate_dashboard_schema(request.question, request.rows)
    except ValidationError as e:
        # LLM returned JSON that failed Pydantic validation — surface the exact fields
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
