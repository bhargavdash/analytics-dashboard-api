"""Ingest an uploaded CSV/XLSX into the DuckDB warehouse as its own table.

Each upload becomes one table in analytics.duckdb (alongside the demo tables). The
dataset's metadata (columns, sample, row count) is introspected here; the app_state
record + suggested questions are persisted by the /datasets endpoint.

Tier note (single-user / hobby): we ingest with a short-lived read-write DuckDB
connection while generated SQL runs on read-only connections. DuckDB file-locks a
read-write connection exclusively, so an upload and a query must not overlap — fine for
one user, serialized here with an asyncio lock. At scale you'd give each tenant its own
database file (or a real warehouse) so ingest and query never contend.
"""

import asyncio
import os
import re
import tempfile
import uuid

import duckdb

from app.db.connection import DATASETS_DB_PATH
from app.services.db_exec import _coerce

MAX_BYTES = 10 * 1024 * 1024  # 10 MB cap
_SAMPLE_ROWS = 5

# Only one ingest (or table drop) at a time — read-write DuckDB access is exclusive.
ingest_lock = asyncio.Lock()


class IngestError(Exception):
    """A user-facing problem with the upload (bad type, too big, unreadable)."""


def _source_from_filename(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".csv":
        return "csv"
    if ext in (".xlsx", ".xls"):
        return "xlsx"
    raise IngestError("unsupported file type — upload a .csv or .xlsx file")


def _sanitize_table_name(filename: str) -> str:
    """A safe, unique DuckDB identifier derived from the filename.

    The uuid prefix guarantees uniqueness and prevents collisions with demo tables
    (orders/products/…) or other uploads, so we never need to parameterize the
    identifier (which SQL can't do anyway)."""
    base = os.path.splitext(os.path.basename(filename or "data"))[0].lower()
    base = re.sub(r"[^a-z0-9_]+", "_", base).strip("_")[:40] or "data"
    return f"ds_{uuid.uuid4().hex[:8]}_{base}"


def _ingest_sync(file_path: str, table_name: str, source: str) -> dict:
    con = duckdb.connect(str(DATASETS_DB_PATH))  # read-write — exclusive while open
    try:
        if source == "csv":
            con.execute(
                f'CREATE TABLE "{table_name}" AS '
                "SELECT * FROM read_csv_auto(?, SAMPLE_SIZE=-1)",
                [file_path],
            )
        else:  # xlsx — needs the excel extension (auto-downloaded on first use)
            con.execute("INSTALL excel")
            con.execute("LOAD excel")
            con.execute(
                f'CREATE TABLE "{table_name}" AS '
                "SELECT * FROM read_xlsx(?, header = true)",
                [file_path],
            )

        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table_name],
        ).fetchall()
        if not cols:
            raise IngestError("could not detect any columns in the file")
        columns = [{"name": c, "type": d} for c, d in cols]

        row_count = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        if row_count == 0:
            con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            raise IngestError("the file has no data rows")

        names = [c["name"] for c in columns]
        sample_rows = con.execute(
            f'SELECT * FROM "{table_name}" LIMIT {_SAMPLE_ROWS}'
        ).fetchall()
        sample = [
            {k: _coerce(v) for k, v in zip(names, row)} for row in sample_rows
        ]

        return {"columns": columns, "row_count": row_count, "sample": sample}
    finally:
        con.close()


async def ingest_dataset(filename: str, content: bytes) -> dict:
    """Validate + ingest the upload, returning metadata for persistence."""
    source = _source_from_filename(filename)
    if not content:
        raise IngestError("the file is empty")
    if len(content) > MAX_BYTES:
        raise IngestError("file is too large (max 10 MB)")

    table_name = _sanitize_table_name(filename)
    suffix = ".csv" if source == "csv" else ".xlsx"

    async with ingest_lock:
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            tmp.write(content)
            tmp.close()
            meta = await asyncio.to_thread(_ingest_sync, tmp.name, table_name, source)
        except duckdb.Error as e:
            raise IngestError(f"could not read the file: {e}")
        finally:
            os.unlink(tmp.name)

    return {
        "name": filename,
        "source": source,
        "table_name": table_name,
        **meta,
    }


def _drop_table_sync(table_name: str) -> None:
    con = duckdb.connect(str(DATASETS_DB_PATH))
    try:
        con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    finally:
        con.close()


async def drop_dataset_table(table_name: str) -> None:
    async with ingest_lock:
        await asyncio.to_thread(_drop_table_sync, table_name)
