"""CSV ingest tests — exercises the real DuckDB ingest against a throwaway DB file."""

import duckdb
import pytest

from app.services import ingest
from app.services.ingest import ingest_dataset, IngestError


@pytest.fixture
def temp_datasets_db(monkeypatch, tmp_path):
    """Redirect ingest at a throwaway datasets.duckdb so we never touch the real one."""
    db_file = tmp_path / "datasets_test.duckdb"
    monkeypatch.setattr(ingest, "DATASETS_DB_PATH", db_file)
    return db_file


async def test_ingest_csv_creates_table(temp_datasets_db, sample_csv_bytes):
    meta = await ingest_dataset("sample.csv", sample_csv_bytes)

    # The backing table actually exists in DuckDB.
    con = duckdb.connect(str(temp_datasets_db), read_only=True)
    try:
        tables = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
    finally:
        con.close()
    assert meta["table_name"] in tables


async def test_ingest_csv_returns_correct_schema(temp_datasets_db, sample_csv_bytes):
    meta = await ingest_dataset("sample.csv", sample_csv_bytes)

    assert meta["row_count"] == 5
    col_names = [c["name"] for c in meta["columns"]]
    assert col_names == ["region", "product", "amount"]
    assert meta["source"] == "csv"
    assert meta["name"] == "sample.csv"


async def test_oversized_file_is_rejected(temp_datasets_db):
    too_big = b"0" * (ingest.MAX_BYTES + 1)
    with pytest.raises(IngestError):
        await ingest_dataset("big.csv", too_big)


async def test_unsupported_extension_is_rejected(temp_datasets_db):
    with pytest.raises(IngestError):
        await ingest_dataset("notes.txt", b"hello")
