import asyncio
import json
from typing import AsyncIterator
from app.services.a2ui_schema import generate_dashboard_schema
from app.services.sql_gen import generate_sql
from app.services.db_exec import run_db_query
from app.db import app_store


def _emit(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


async def run_query(question: str, conversation_id: str | None = None) -> AsyncIterator[str]:
    # Collect the reasoning trace as we stream so it can be persisted with the turn.
    # Shape mirrors the FE ReasoningStep ({tool, title}) so no transform is needed on read.
    events: list[dict] = []

    def reason(step: str, message: str) -> str:
        events.append({"tool": step, "title": message})
        return _emit("reasoning", {"step": step, "message": message})

    try:
        # New conversation on first question; follow-ups reuse the id from the client.
        if conversation_id is None:
            conversation_id = await asyncio.to_thread(
                app_store.create_conversation, question
            )
            history: list[dict] = []
        else:
            history = await asyncio.to_thread(
                app_store.get_recent_turns, conversation_id
            )

        # Tell the client which conversation this turn belongs to, before any work —
        # lets the UI associate the stream and refresh its sidebar immediately.
        yield _emit("meta", {"conversation_id": conversation_id, "is_followup": bool(history)})

        yield reason("parse", f"Understanding: {question}")

        yield reason("sql_gen", "Generating SQL query...")
        sql = await generate_sql(question, history)
        yield reason("sql_gen", f"SQL ready: {sql}")

        yield reason("db_exec", "Running query on DuckDB...")
        rows = await run_db_query(sql)
        yield reason("db_exec", f"Got {len(rows)} rows")

        yield reason("a2ui_schema", "Generating dashboard schema...")
        schema = await generate_dashboard_schema(question, rows)

        widgets = [w.model_dump() for w in schema.widgets]

        # Persist the completed turn (and bump the conversation's updated_at).
        await asyncio.to_thread(
            app_store.add_turn,
            conversation_id,
            question,
            sql,
            schema.summary,
            widgets,
            events,
        )

        yield _emit("dashboard", schema.model_dump())
        yield _emit("done", {"message": "Complete"})
    except Exception as e:
        # Errors after the first byte can't become an HTTP error code — the 200 is
        # already sent. Emit an in-band error event so the stream closes cleanly.
        yield _emit("error", {"message": f"{type(e).__name__}: {e}"})
