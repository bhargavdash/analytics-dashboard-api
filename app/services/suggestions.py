"""Generate 3 starter questions for a freshly-uploaded dataset from its schema card.

Small JSON-mode LLM call. Failure is non-fatal — the upload still succeeds with an
empty suggestion list, the UI just won't show chips."""

import os
import json
import logging

from openai import AsyncOpenAI

logger = logging.getLogger("helix")

client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    timeout=30.0,
)

_SYSTEM_PROMPT = """You generate starter questions for a data-analytics assistant.
Given a table's schema (columns, categorical values, sample rows), produce exactly 3
concise, concrete natural-language questions a business user would ask of THIS data.

- Each must be answerable by a SQL aggregation over the columns shown (trends, top-N,
  breakdowns, comparisons). Prefer questions that make a good chart.
- Be specific to the actual columns/values — no generic "show me the data".
- Keep each under 12 words. No numbering, no trailing punctuation beyond a question mark.

Respond as JSON: {"questions": ["...", "...", "..."]}"""


async def generate_suggestions(schema_card: str) -> list[str]:
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Schema:\n{schema_card}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        data = json.loads(response.choices[0].message.content)
        questions = data.get("questions", [])
        # Defensive: keep only non-empty strings, cap at 3.
        return [q for q in questions if isinstance(q, str) and q.strip()][:3]
    except Exception as e:
        logger.warning("suggestion generation failed: %s", e)
        return []
