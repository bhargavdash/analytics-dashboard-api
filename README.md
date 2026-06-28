# Helix API

FastAPI backend for the Helix conversational data analyst. Handles intent classification, SQL generation, DuckDB execution, and SSE streaming. See the [frontend README](../analytics-dashboard-ui/README.md) for the full project overview.

---

## Endpoints

### Query

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/query` | Stream an agent response for a natural-language question |

**Request body:**
```json
{
  "question": "What were our top regions last quarter?",
  "conversation_id": "optional — omit to start a new conversation",
  "dataset_id": "optional — omit to use the built-in demo dataset"
}
```

**SSE events emitted (in order):**
```
event: meta           data: { "conversation_id": "...", "is_followup": false }
event: reasoning      data: { "step": "route", "label": "Classifying intent..." }
event: summary_token  data: { "token": "Revenue " }   ← one per token, N times
event: dashboard      data: { "widgets": [...] }       ← validated widget specs
event: done           data: {}
event: error          data: { "message": "..." }       ← emitted on failure, in-band
```

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/conversations` | List all conversations (id, title, created_at) |
| `GET` | `/api/v1/conversations/:id` | Full conversation with all turns and events |
| `PATCH` | `/api/v1/conversations/:id` | Rename `{ "title": "..." }` |
| `DELETE` | `/api/v1/conversations/:id` | Delete conversation and all its turns |

### Datasets

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/datasets` | Upload a CSV or XLSX file (multipart, 10 MB cap) |
| `GET` | `/api/v1/datasets` | List uploaded datasets |
| `GET` | `/api/v1/datasets/:id` | Dataset schema + sample rows + suggested questions |
| `DELETE` | `/api/v1/datasets/:id` | Delete dataset record and drop the DuckDB table |

### Schema / Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/schema` | Demo dataset schema (columns + sample) |
| `GET` | `/health` | Health check — `{ "status": "ok" }` |

---

## App structure

```
app/
  main.py              FastAPI app, CORS, router registration
  api/
    stream.py          POST /query — SSE orchestration entry point
    conversations.py   conversation CRUD
    datasets.py        dataset upload + CRUD
    schema.py          schema introspection endpoint
  services/
    router.py          intent classifier (JSON-mode LLM call)
    sql_gen.py         NLQ → SQL (LLM, schema-grounded)
    sql_safety.py      allowlist guard + LIMIT enforcement
    a2ui_schema.py     rows → widget specs (JSON-mode) + prose insight (streaming)
    schema_card.py     builds the grounding card (columns + categoricals + few-shot)
    ingest.py          CSV/XLSX → DuckDB ingest
    suggestions.py     LLM-generated starter questions from uploaded schema
  db/
    connection.py      DuckDB connection + DATA_DIR resolution
    app_store.py       SQLite schema (conversations/turns), CRUD helpers
    db_exec.py         safe DuckDB query execution, _coerce() for JSON serialisation
    seed.py            seeds analytics.duckdb with 200k synthetic rows
db/
  analytics.duckdb     pre-seeded demo warehouse (read-only at runtime)
  datasets.duckdb      user uploads (created on first upload)
  app_state.db         conversations + turns (created on boot)
tests/
  conftest.py          tmp-db isolation, placeholder API key
  test_router.py       intent classification with mocked LLM
  test_sql_safety.py   allowlist, DML rejection, LIMIT enforcement
  test_db_exec.py      _coerce() type normalisation
  test_ingest.py       CSV ingest, row count, size cap
  test_api_conversations.py  TestClient integration tests
```

---

## Running locally

```bash
uv sync

cp .env.example .env
# → set OPENROUTER_API_KEY

uv run uvicorn app.main:app --reload --port 8001
```

## Running tests

```bash
pytest tests/ -v
```

Dev dependencies (`pytest`, `pytest-asyncio`, `httpx`) live in `requirements-dev.txt` — install into the venv with `uv pip install -r requirements-dev.txt` if needed.

---

## Storage

All persistent files live under `DATA_DIR` (env var, defaults to `./db`):

| File | Type | Access |
|------|------|--------|
| `analytics.duckdb` | DuckDB | Read-only — the pre-seeded demo warehouse |
| `datasets.duckdb` | DuckDB | Read-write — user-uploaded datasets |
| `app_state.db` | SQLite | Read-write — conversations + turns |

In production (Railway), set `DATA_DIR=/data` and mount a persistent volume at `/data`. On first boot, `start.sh` copies `analytics.duckdb` from the image to the volume. Subsequent deploys find it already there.

---

## Key design decisions

**Two DuckDB files** — keeping the demo warehouse read-only means a DB viewer can stay open without blocking ingest. Uploads go to a separate writable file so an upload never locks a demo query.

**Dependency-inverted schema grounding** — `router.py` and `sql_gen.py` accept a schema card as an argument rather than importing a global `get_schema_card()`. The orchestrator resolves the right card (demo or per-upload) and injects it. This keeps both services dataset-agnostic and independently testable.

**Tier-2 agent** — the router classifies intent up front; Python branches to the right path. A full tool-calling loop (Tier 3 / LangGraph) is the "next tier" answer — deferred because non-deterministic step order breaks the streaming reasoning trace and adds latency.

**In-band error events** — errors raised inside an SSE generator after the first byte is flushed can't become HTTP error responses. The orchestrator wraps the generator body in `try/except` and emits `event: error` so the client always gets a clean signal.
