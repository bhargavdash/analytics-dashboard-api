"""The router (planner): classifies the user's message and chooses the path.

This is what makes Helix a data *agent* rather than a fixed pipeline — only a real
data question runs SQL; everything else gets a conversational reply. Grounded against
the schema so it can answer "what data do you have?" and decline the un-answerable.
"""

import os
import json
from typing import Literal
from pydantic import BaseModel, ValidationError
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    timeout=30.0,
)

Intent = Literal[
    "data_question",
    "greeting",
    "about_data",
    "clarification_needed",
    "out_of_scope",
]


class RouterDecision(BaseModel):
    intent: Intent
    # Conversational reply for every intent except data_question (which runs SQL).
    reply: str | None = None


def _system_prompt(schema_card: str) -> str:
    return f"""You are the router for "Helix", a data analytics assistant. Classify the
user's latest message into exactly one intent and respond as JSON.

The data you can analyze:
{schema_card}

Respond as JSON: {{"intent": "<intent>", "reply": "<text or null>"}}

Intents:
- data_question: answerable by querying the data above. Set reply to null.
- greeting: hi/hello/thanks/small talk. reply = a short, warm greeting that invites a
  data question (refer to the dataset above, not a generic one).
- about_data: asking what data/tables/columns/values exist. reply = answer concisely
  from the schema above.
- clarification_needed: a data request too vague to query (missing metric, timeframe,
  or dimension). reply = ONE short clarifying question.
- out_of_scope: not answerable from this data (weather, general knowledge, coding, etc).
  reply = a brief, polite decline that redirects to what you can analyze.

Use the conversation history to resolve follow-ups ("now break that down" after a data
question is itself a data_question). Output ONLY the JSON object."""


def _history_block(history: list[dict] | None) -> str:
    if not history:
        return ""
    lines = ["Conversation so far (oldest first):"]
    for turn in history:
        kind = "data query" if turn.get("sql") else "reply"
        lines.append(f"- user: {turn['question']}  (assistant gave a {kind})")
    return "\n".join(lines) + "\n\n"


async def classify(
    question: str, history: list[dict] | None = None, schema_card: str = ""
) -> RouterDecision:
    user_content = _history_block(history) + f"Latest message: {question}"
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": _system_prompt(schema_card)},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    raw = response.choices[0].message.content
    try:
        return RouterDecision.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        # Fail safe: if the router misbehaves, treat it as a data question so the
        # downstream pipeline (with its own guards) still gets a chance.
        return RouterDecision(intent="data_question", reply=None)
