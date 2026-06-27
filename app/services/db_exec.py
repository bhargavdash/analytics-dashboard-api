import asyncio
import datetime
from decimal import Decimal
import duckdb
from app.models.widgets import DataRow

DB_PATH = "analytics.duckdb"


def _coerce(value):
    """Normalize DB-native types into JSON-safe primitives.

    DuckDB returns DECIMAL as decimal.Decimal and DATE/TIMESTAMP as
    datetime objects — neither is JSON-serializable, and both violate the
    DataRow contract (str | int | float | None). This is the boundary where
    raw DB types enter the system, so coerce here once.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _run_query(sql: str) -> list[DataRow]:
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError(f"Only SELECT queries allowed. Got: {sql[:60]}")

    con = duckdb.connect(DB_PATH, read_only=True)
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


async def run_db_query(sql: str) -> list[DataRow]:
    return await asyncio.to_thread(_run_query, sql)