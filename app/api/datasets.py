"""Bring-your-own-data: upload a CSV/XLSX, list/inspect/delete datasets."""

import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File

from app.db import app_store
from app.services.ingest import ingest_dataset, drop_dataset_table, IngestError
from app.services.schema_card import build_dataset_schema_card
from app.services.suggestions import generate_suggestions
from app.models.dataset import DatasetRecord

router = APIRouter()


@router.post("/datasets", response_model=DatasetRecord)
async def upload_dataset(file: UploadFile = File(...)):
    content = await file.read()
    try:
        ing = await ingest_dataset(file.filename or "upload", content)
    except IngestError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Build the grounded card (cached) and generate starter questions from it.
    card = await asyncio.to_thread(build_dataset_schema_card, ing["table_name"])
    suggestions = await generate_suggestions(card)

    did = await asyncio.to_thread(
        app_store.create_dataset,
        ing["name"],
        ing["source"],
        ing["table_name"],
        ing["columns"],
        ing["sample"],
        suggestions,
        ing["row_count"],
    )
    return await asyncio.to_thread(app_store.get_dataset, did)


@router.get("/datasets", response_model=list[DatasetRecord])
async def list_datasets():
    return await asyncio.to_thread(app_store.list_datasets)


@router.get("/datasets/{dataset_id}", response_model=DatasetRecord)
async def get_dataset(dataset_id: str):
    rec = await asyncio.to_thread(app_store.get_dataset, dataset_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return rec


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str):
    rec = await asyncio.to_thread(app_store.delete_dataset, dataset_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    # Drop the backing DuckDB table too (best-effort; the record is already gone).
    await drop_dataset_table(rec["table_name"])
    return {"deleted": dataset_id}
