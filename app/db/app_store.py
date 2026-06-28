"""OLTP app-state store (SQLite) — conversations, turns, and their event logs.

Deliberately SEPARATE from analytics.duckdb:
  - analytics.duckdb is the OLAP warehouse (read-only for LLM-generated queries).
  - This is OLTP: write-heavy, single-row lookups, app metadata. SQLite is the fit.
Keeping them apart also avoids lock contention against db_exec's read_only handles.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

# Path resolved centrally (honors DATA_DIR for deploys with a persistent volume).
from app.db.connection import APP_STATE_DB_PATH as DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    # New connection per operation: SQLite is fast to open and this sidesteps
    # cross-thread sharing issues with FastAPI's async + asyncio.to_thread.
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db() -> None:
    con = _connect()
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                dataset     TEXT NOT NULL DEFAULT 'sales',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS turns (
                id              TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                seq             INTEGER NOT NULL,
                question        TEXT NOT NULL,
                sql             TEXT,
                summary         TEXT,
                widgets_json    TEXT NOT NULL DEFAULT '[]',
                events_json     TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_turns_conversation
                ON turns(conversation_id, seq);

            -- Phase B: user-uploaded datasets. One row per ingested file; the actual
            -- columnar data lives in analytics.duckdb under `table_name`.
            CREATE TABLE IF NOT EXISTS datasets (
                id               TEXT PRIMARY KEY,
                name             TEXT NOT NULL,          -- original filename (display)
                source           TEXT NOT NULL,          -- 'csv' | 'xlsx'
                table_name       TEXT NOT NULL UNIQUE,   -- sanitized DuckDB table
                columns_json     TEXT NOT NULL DEFAULT '[]',
                sample_json      TEXT NOT NULL DEFAULT '[]',
                suggestions_json TEXT NOT NULL DEFAULT '[]',
                row_count        INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL
            );
            """
        )
        # Migrate: add conversations.dataset_id (null = built-in demo dataset) if absent.
        cols = {r["name"] for r in con.execute("PRAGMA table_info(conversations)").fetchall()}
        if "dataset_id" not in cols:
            con.execute("ALTER TABLE conversations ADD COLUMN dataset_id TEXT")
        con.commit()
    finally:
        con.close()


def create_conversation(
    title: str, dataset_id: str | None = None, dataset_label: str = "sales"
) -> str:
    cid = str(uuid.uuid4())
    now = _now()
    # Title is the first question, trimmed for the sidebar.
    title = (title[:80] + "…") if len(title) > 80 else title
    con = _connect()
    try:
        con.execute(
            "INSERT INTO conversations (id, title, dataset, dataset_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cid, title, dataset_label, dataset_id, now, now),
        )
        con.commit()
    finally:
        con.close()
    return cid


def add_turn(
    conversation_id: str,
    question: str,
    sql: str | None,
    summary: str | None,
    widgets: list,
    events: list,
) -> str:
    tid = str(uuid.uuid4())
    now = _now()
    con = _connect()
    try:
        row = con.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM turns WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        seq = (row["m"] or 0) + 1
        con.execute(
            "INSERT INTO turns "
            "(id, conversation_id, seq, question, sql, summary, widgets_json, events_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tid,
                conversation_id,
                seq,
                question,
                sql,
                summary,
                json.dumps(widgets),
                json.dumps(events),
                now,
            ),
        )
        con.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        con.commit()
    finally:
        con.close()
    return tid


def list_conversations() -> list[dict]:
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT
                c.id, c.title, c.dataset, c.created_at, c.updated_at,
                COUNT(t.id) AS turn_count,
                (SELECT json_array_length(widgets_json)
                   FROM turns
                  WHERE conversation_id = c.id
                  ORDER BY seq DESC LIMIT 1) AS widget_count
            FROM conversations c
            LEFT JOIN turns t ON t.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def _turn_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "seq": row["seq"],
        "question": row["question"],
        "sql": row["sql"],
        "summary": row["summary"],
        "widgets": json.loads(row["widgets_json"]),
        "reasoningSteps": json.loads(row["events_json"]),
        "created_at": row["created_at"],
    }


def get_conversation(conversation_id: str) -> dict | None:
    con = _connect()
    try:
        c = con.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if c is None:
            return None
        turns = con.execute(
            "SELECT * FROM turns WHERE conversation_id = ? ORDER BY seq ASC",
            (conversation_id,),
        ).fetchall()
        return {
            "id": c["id"],
            "title": c["title"],
            "dataset": c["dataset"],
            "dataset_id": c["dataset_id"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
            "turns": [_turn_to_dict(t) for t in turns],
        }
    finally:
        con.close()


def get_recent_turns(conversation_id: str, limit: int = 4) -> list[dict]:
    """Prior turns (question + SQL) used to give the SQL generator follow-up context."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT question, sql FROM turns WHERE conversation_id = ? "
            "ORDER BY seq DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        con.close()


def rename_conversation(conversation_id: str, title: str) -> bool:
    title = (title[:80] + "…") if len(title) > 80 else title
    con = _connect()
    try:
        cur = con.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), conversation_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def delete_conversation(conversation_id: str) -> bool:
    con = _connect()
    try:
        cur = con.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def get_conversation_dataset_id(conversation_id: str) -> str | None:
    """Which dataset a thread is scoped to (None = built-in demo)."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT dataset_id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return row["dataset_id"] if row else None
    finally:
        con.close()


# --- Datasets (Phase B) ---

def _dataset_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "source": row["source"],
        "table_name": row["table_name"],
        "columns": json.loads(row["columns_json"]),
        "sample": json.loads(row["sample_json"]),
        "suggestions": json.loads(row["suggestions_json"]),
        "row_count": row["row_count"],
        "created_at": row["created_at"],
    }


def create_dataset(
    name: str,
    source: str,
    table_name: str,
    columns: list,
    sample: list,
    suggestions: list,
    row_count: int,
) -> str:
    did = str(uuid.uuid4())
    con = _connect()
    try:
        con.execute(
            "INSERT INTO datasets "
            "(id, name, source, table_name, columns_json, sample_json, suggestions_json, row_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                did,
                name,
                source,
                table_name,
                json.dumps(columns),
                json.dumps(sample),
                json.dumps(suggestions),
                row_count,
                _now(),
            ),
        )
        con.commit()
    finally:
        con.close()
    return did


def list_datasets() -> list[dict]:
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM datasets ORDER BY created_at DESC"
        ).fetchall()
        return [_dataset_to_dict(r) for r in rows]
    finally:
        con.close()


def get_dataset(dataset_id: str) -> dict | None:
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        return _dataset_to_dict(row) if row else None
    finally:
        con.close()


def delete_dataset(dataset_id: str) -> dict | None:
    """Delete the dataset row and return it (so the caller can drop the DuckDB table)."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if row is None:
            return None
        rec = _dataset_to_dict(row)
        con.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        con.commit()
        return rec
    finally:
        con.close()
