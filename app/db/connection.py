# Duck db connection singleton 

import duckdb
import os 
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "analytics.duckdb"

_conn: duckdb.DuckDBPyConnection | None = None

def get_connection() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(str(DB_PATH))
    return _conn
