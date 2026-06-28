# DuckDB / SQLite file locations — the single source of truth for where state lives on disk.
#
# All persistent files live under DATA_DIR so a deployment can point them at a mounted volume
# (e.g. Railway Volumes at /data) instead of ephemeral container storage. Locally it defaults
# to ./db inside the API project, so a fresh clone "just works".
#
# Two separate DuckDB files, on purpose:
#   - WAREHOUSE: the built-in demo dataset. The app only ever opens it READ-ONLY, so it never
#     write-locks the file (a DB viewer can stay open alongside it).
#   - DATASETS:  user uploads (Phase B). Written read-write at ingest, read-only at query.
# Keeping them apart insulates the demo from upload writes and from cross-file locking.

import os
import duckdb
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent

# Base directory for all on-disk state. Override with DATA_DIR (absolute path recommended in
# production, e.g. DATA_DIR=/data). Created on import so first boot on a fresh volume succeeds.
DATA_DIR = Path(os.getenv("DATA_DIR", str(_ROOT / "db")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

WAREHOUSE_DB_PATH = DATA_DIR / "analytics.duckdb"
DATASETS_DB_PATH = DATA_DIR / "datasets.duckdb"
APP_STATE_DB_PATH = DATA_DIR / "app_state.db"

# Back-compat alias (the demo warehouse).
DB_PATH = WAREHOUSE_DB_PATH

_conn: duckdb.DuckDBPyConnection | None = None

def get_connection() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(str(WAREHOUSE_DB_PATH))
    return _conn
