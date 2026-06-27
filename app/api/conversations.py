"""Read/manage persisted conversations (the sidebar's past dashboards)."""

import asyncio
from fastapi import APIRouter, HTTPException
from app.db import app_store
from app.models.conversation import ConversationMeta, ConversationDetail

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationMeta])
async def list_conversations():
    return await asyncio.to_thread(app_store.list_conversations)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str):
    convo = await asyncio.to_thread(app_store.get_conversation, conversation_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return convo


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    ok = await asyncio.to_thread(app_store.delete_conversation, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": conversation_id}
