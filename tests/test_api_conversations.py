"""Integration tests via FastAPI TestClient.

Routes are mounted under the /api/v1 prefix (see app/main.py). The LLM is mocked at the
orchestrator boundary so the greeting path runs end-to-end without a network call.
"""

import pytest

from app.services import orchestrator
from app.services.router import RouterDecision


@pytest.fixture
def mock_greeting_router(monkeypatch):
    """Force the router to classify the next message as a greeting."""

    async def fake_classify(question, history=None, schema_card=""):
        return RouterDecision(intent="greeting", reply="Hi! Ask me about your sales data.")

    monkeypatch.setattr(orchestrator, "classify", fake_classify)


def test_query_greeting_streams_message_event(client, mock_greeting_router):
    resp = client.post("/api/v1/query", json={"question": "hello"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    # The greeting branch emits a `message` event carrying the reply, then `done`.
    assert "event: message" in body
    assert "Ask me about your sales data" in body
    assert "event: done" in body


def test_list_conversations_returns_list(client, temp_app_store):
    temp_app_store.create_conversation("First question", None, "sales")
    resp = client.get("/api/v1/conversations")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["title"] == "First question"


def test_rename_conversation(client, temp_app_store):
    cid = temp_app_store.create_conversation("Old title", None, "sales")
    resp = client.patch(f"/api/v1/conversations/{cid}", json={"title": "New title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New title"
    # Persisted.
    assert temp_app_store.get_conversation(cid)["title"] == "New title"


def test_delete_conversation(client, temp_app_store):
    cid = temp_app_store.create_conversation("To delete", None, "sales")
    resp = client.delete(f"/api/v1/conversations/{cid}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == cid
    assert temp_app_store.get_conversation(cid) is None


def test_rename_missing_conversation_returns_404(client):
    resp = client.patch("/api/v1/conversations/does-not-exist", json={"title": "x"})
    assert resp.status_code == 404
