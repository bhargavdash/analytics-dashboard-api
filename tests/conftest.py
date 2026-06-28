"""Shared pytest fixtures and test-time environment setup.

Set dummy API keys BEFORE any app module is imported: app.services.router builds an
AsyncOpenAI client at import time from GROQ_API_KEY, and would raise without one. The
real LLM is always mocked in tests, so a placeholder key is all we need.
"""

import os

os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_csv_bytes() -> bytes:
    """A small CSV: 5 data rows, 3 columns (region, product, amount)."""
    return (FIXTURES / "sample.csv").read_bytes()


@pytest.fixture
def temp_app_store(monkeypatch, tmp_path):
    """Point the SQLite app-state store at a throwaway DB and create its schema.

    app_store reads its module-level DB_PATH inside _connect() on every call, so
    redirecting that global fully isolates the test from the real app_state.db.
    """
    from app.db import app_store

    db_file = tmp_path / "app_state_test.db"
    monkeypatch.setattr(app_store, "DB_PATH", str(db_file))
    app_store.init_db()
    return app_store


@pytest.fixture
def client(temp_app_store):
    """FastAPI TestClient wired to the isolated app-state store."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c
