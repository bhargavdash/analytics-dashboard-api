import asyncio
import datetime
from decimal import Decimal
import duckdb
from app.models.widgets import DataRow
from app.services.sql_safety import validate_sql, enforce_limit
from app.db.connection import WAREHOUSE_DB_PATH

# Default target = the read-only demo warehouse. The orchestrator passes the datasets
# DB path instead when a conversation is scoped to an uploaded dataset.
DB_PATH = str(WAREHOUSE_DB_PATH)
QUERY_TIMEOUT_S = 20.0


class QueryExecutionError(Exception):
    """Any failure running generated SQL (unsafe, syntax, runtime, timeout).

    Collapsing these into one type lets the orchestrator catch a single thing and
    drive the self-repair loop (feed the message back to the model)."""


def _coerce(value):
    """Normalize DB-native types into JSON-safe primitives.

    DuckDB returns DECIMAL as decimal.Decimal and DATE/TIMESTAMP as datetime objects —
    neither is JSON-serializable, and both violate the DataRow contract."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _run_query(sql: str, db_path: str) -> list[DataRow]:
    con = duckdb.connect(db_path, read_only=True)
    try:
        result = con.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [
            {col: _coerce(val) for col, val in zip(columns, row)}
            for row in rows
        ]
    finally:
        con.close()


async def run_db_query(sql: str, db_path: str = DB_PATH) -> list[DataRow]:
    # Guardrails first (allowlist + statement check + hard LIMIT), then execute.
    try:
        safe_sql = enforce_limit(validate_sql(sql))
    except ValueError as e:
        raise QueryExecutionError(f"unsafe SQL: {e}")

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run_query, safe_sql, db_path), timeout=QUERY_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        raise QueryExecutionError(f"query timed out after {QUERY_TIMEOUT_S:.0f}s")
    except duckdb.Error as e:
        raise QueryExecutionError(str(e))
