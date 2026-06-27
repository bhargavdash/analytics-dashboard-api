import os
import re
from openai import AsyncOpenAI
from app.services.schema_card import get_schema_card

client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    timeout=30.0,
)


def _system_prompt() -> str:
    return f"""You are a SQL expert. Given a business question, write a single DuckDB SQL SELECT query.

Database schema:
{get_schema_card()}

Rules:
- Output ONLY the SQL query. No explanation, no markdown, no code fences.
- Only SELECT statements (a CTE with WITH is fine). Never INSERT, UPDATE, DELETE, DROP.
- Use DuckDB date syntax (date_trunc, strftime) for date operations.
- Use the exact categorical values listed in the schema.
- Always include LIMIT 500.
- Join tables when needed."""


def _history_block(history: list[dict] | None) -> str:
    if not history:
        return ""
    lines = ["\n\nEarlier in this conversation (oldest first):"]
    for turn in history:
        lines.append(f"- Q: {turn['question']}")
        if turn.get("sql"):
            lines.append(f"  SQL: {turn['sql']}")
    lines.append(
        "\nThe new question may build on the above. Resolve any references "
        "(it/that/those/them) against the previous queries."
    )
    return "\n".join(lines)


def _repair_block(previous_sql: str | None, error: str | None) -> str:
    if not error:
        return ""
    return (
        f"\n\nYour previous SQL failed when executed:\n{previous_sql}\n\n"
        f"Error: {error}\n\nFix the query and output ONLY the corrected SQL."
    )


async def generate_sql(
    question: str,
    history: list[dict] | None = None,
    previous_sql: str | None = None,
    error_feedback: str | None = None,
) -> str:
    user_content = question + _history_block(history) + _repair_block(previous_sql, error_feedback)
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:sql)?\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()
