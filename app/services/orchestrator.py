import json
from typing import AsyncIterator
from app.services.a2ui_schema import generate_dashboard_schema
from app.services.sql_gen import generate_sql
from app.services.db_exec import run_db_query


def _emit(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


async def run_query(question: str) -> AsyncIterator[str]:
    try:
        yield _emit("reasoning", {"step": "parse", "message": f"Understanding: {question}"})

        yield _emit("reasoning", {"step": "sql_gen", "message": "Generating SQL query..."})
        sql = await generate_sql(question)
        yield _emit("reasoning", {"step": "sql_gen", "message": f"SQL ready: {sql}"})

        yield _emit("reasoning", {"step": "db_exec", "message": "Running query on DuckDB..."})
        rows = await run_db_query(sql)
        yield _emit("reasoning", {"step": "db_exec", "message": f"Got {len(rows)} rows"})

        yield _emit("reasoning", {"step": "a2ui_schema", "message": "Generating dashboard schema..."})
        schema = await generate_dashboard_schema(question, rows)

        yield _emit("dashboard", schema.model_dump())
        yield _emit("done", {"message": "Complete"})
    except Exception as e:
        # Without this, any exception kills the generator after headers are already
        # flushed — the browser sees a 200 with a truncated/"failed" stream and no
        # clue why. Emitting an error event closes the stream cleanly and tells the UI.
        yield _emit("error", {"message": f"{type(e).__name__}: {e}"})