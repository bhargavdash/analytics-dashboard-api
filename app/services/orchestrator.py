import asyncio
import json
import logging
from typing import AsyncIterator
from app.services.router import classify
from app.services.a2ui_schema import generate_widgets, stream_insight
from app.services.sql_gen import generate_sql
from app.services.db_exec import run_db_query, QueryExecutionError
from app.services.schema_card import resolve_schema_card
from app.db.connection import WAREHOUSE_DB_PATH, DATASETS_DB_PATH
from app.db import app_store

logger = logging.getLogger("helix")

MAX_SQL_ATTEMPTS = 3  # initial try + repairs


def _emit(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


async def run_query(
    question: str,
    conversation_id: str | None = None,
    dataset_id: str | None = None,
) -> AsyncIterator[str]:
    """Route the message, then run only the steps that intent requires.

    Non-data intents (greeting/about_data/clarify/out_of_scope) get a text `message`
    reply. A data question runs sql_gen → (validate+repair) → db_exec → a2ui. Each
    branch persists a turn; a thin try/except emits an in-band error if anything escapes.

    `dataset_id` scopes the thread: it comes from the request for a new conversation and
    from the stored conversation for follow-ups (None = built-in demo warehouse).
    """
    events: list[dict] = []

    def reason(step: str, message: str) -> str:
        events.append({"tool": step, "title": message})
        return _emit("reasoning", {"step": step, "message": message})

    try:
        # New conversation on first message; follow-ups reuse the id + load history.
        if conversation_id is None:
            history: list[dict] = []
            dataset = await asyncio.to_thread(app_store.get_dataset, dataset_id) if dataset_id else None
            label = dataset["name"] if dataset else "sales"
            conversation_id = await asyncio.to_thread(
                app_store.create_conversation, question, dataset_id, label
            )
        else:
            history = await asyncio.to_thread(app_store.get_recent_turns, conversation_id)
            dataset_id = await asyncio.to_thread(
                app_store.get_conversation_dataset_id, conversation_id
            )
            dataset = await asyncio.to_thread(app_store.get_dataset, dataset_id) if dataset_id else None

        # Resolve the grounded schema card once and inject it into the router + sql_gen.
        # The dataset also decides which DuckDB file the SQL runs against.
        schema_card = await asyncio.to_thread(resolve_schema_card, dataset)
        db_path = str(DATASETS_DB_PATH if dataset else WAREHOUSE_DB_PATH)

        yield _emit("meta", {"conversation_id": conversation_id, "is_followup": bool(history)})

        # --- ROUTE ---
        yield reason("route", "Understanding your question…")
        decision = await classify(question, history, schema_card)
        logger.info("intent=%s dataset=%s q=%r", decision.intent, dataset_id, question)

        # --- NON-DATA BRANCHES → conversational reply ---
        if decision.intent != "data_question":
            reply = decision.reply or "I can help you analyze your sales data — ask me a question about it."
            await asyncio.to_thread(
                app_store.add_turn, conversation_id, question, None, reply, [], events
            )
            yield _emit("message", {"message": reply, "intent": decision.intent})
            yield _emit("done", {"message": "Complete"})
            return

        # --- DATA BRANCH: sql_gen with self-repair loop ---
        yield reason("sql_gen", "Generating SQL query…")
        sql = ""
        rows = None
        previous_sql: str | None = None
        error_feedback: str | None = None

        for attempt in range(MAX_SQL_ATTEMPTS):
            sql = await generate_sql(question, history, schema_card, previous_sql, error_feedback)
            yield reason("sql_gen", f"SQL ready: {sql}")

            yield reason("db_exec", "Running query on DuckDB…")
            try:
                rows = await run_db_query(sql, db_path)
                break
            except QueryExecutionError as e:
                logger.warning("sql attempt %d failed: %s", attempt + 1, e)
                if attempt == MAX_SQL_ATTEMPTS - 1:
                    raise
                previous_sql, error_feedback = sql, str(e)
                yield reason("db_exec", f"Query failed — repairing ({e})")

        assert rows is not None
        yield reason("db_exec", f"Got {len(rows)} rows")

        # --- NO RESULTS → conversational reply, no empty chart ---
        if len(rows) == 0:
            reply = "I ran the query but found no matching data. Try a different timeframe or filter."
            await asyncio.to_thread(
                app_store.add_turn, conversation_id, question, sql, reply, [], events
            )
            yield _emit("message", {"message": reply, "intent": "data_question"})
            yield _emit("done", {"message": "Complete"})
            return

        # --- INSIGHT (streamed prose) ---
        # Stream the interpretation token-by-token so it materializes in the UI instead
        # of popping in whole. The joined text is the canonical summary we persist.
        yield reason("a2ui_schema", "Interpreting the results…")
        summary_parts: list[str] = []
        async for token in stream_insight(question, rows):
            summary_parts.append(token)
            yield _emit("summary_token", {"token": token})
        summary = "".join(summary_parts).strip()

        # --- CHARTS (structured) ---
        yield reason("a2ui_schema", "Designing the charts…")
        widgets = [w.model_dump() for w in await generate_widgets(question, rows)]

        await asyncio.to_thread(
            app_store.add_turn, conversation_id, question, sql, summary, widgets, events
        )
        # Summary already streamed via summary_token; this event only carries the charts.
        yield _emit("dashboard", {"widgets": widgets})
        yield _emit("done", {"message": "Complete"})

    except Exception as e:
        logger.exception("run_query failed")
        yield _emit("error", {"message": f"{type(e).__name__}: {e}"})
