"""Router (intent classifier) tests.

The routing decision is made by the LLM, so we mock the underlying OpenAI/Groq call
(`client.chat.completions.create`) and assert that `classify` parses the model's JSON
into the correct intent. The fake keys its response off the latest user message so each
assertion exercises a different branch.
"""

import json
from types import SimpleNamespace

import pytest

from app.services import router


def _fake_completion(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _intent_for(question: str) -> str:
    q = question.lower()
    if "hello" in q or "hi" in q:
        return "greeting"
    if "what can you tell me about the data" in q or "what data" in q:
        return "about_data"
    return "data_question"


async def _fake_create(*args, **kwargs):
    # The latest user message is the last entry in the messages list.
    user_content = kwargs["messages"][-1]["content"]
    intent = _intent_for(user_content)
    reply = None if intent == "data_question" else "ok"
    return _fake_completion(json.dumps({"intent": intent, "reply": reply}))


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    monkeypatch.setattr(router.client.chat.completions, "create", _fake_create)


async def test_greeting_routes_to_greeting():
    decision = await router.classify("Hello")
    assert decision.intent == "greeting"


async def test_data_question_routes_to_data_question():
    decision = await router.classify("What were our top regions last quarter?")
    assert decision.intent == "data_question"
    # data_question carries no conversational reply — it runs SQL instead.
    assert decision.reply is None


async def test_about_data_routes_to_about_data():
    decision = await router.classify("What can you tell me about the data?")
    assert decision.intent == "about_data"


async def test_malformed_json_falls_back_to_data_question(monkeypatch):
    async def bad_create(*args, **kwargs):
        return _fake_completion("not json at all")

    monkeypatch.setattr(router.client.chat.completions, "create", bad_create)
    decision = await router.classify("anything")
    assert decision.intent == "data_question"
