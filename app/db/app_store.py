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
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "app_state.db"


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
            """
        )
        con.commit()
    finally:
        con.close()


def create_conversation(title: str, dataset: str = "sales") -> str:
    cid = str(uuid.uuid4())
    now = _now()
    # Title is the first question, trimmed for the sidebar.
    title = (title[:80] + "…") if len(title) > 80 else title
    con = _connect()
    try:
        con.execute(
            "INSERT INTO conversations (id, title, dataset, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cid, title, dataset, now, now),
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
