import os
import re
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

SCHEMA = """
  orders(order_id, customer_id, product_id, region, sales_rep_id, order_date DATE, amount DECIMAL, status)
  products(product_id, name, category, unit_price DECIMAL)
  customers(customer_id, name, segment, country)
  sales_reps(sales_rep_id, name, region, team)
"""

SYSTEM_PROMPT = f"""You are a SQL expert. Given a business question, write a single DuckDB SQL SELECT query.

Database schema:
{SCHEMA}

Rules:
- Output ONLY the SQL query. No explanation, no markdown, no code fences.
- Only SELECT statements. Never INSERT, UPDATE, DELETE, DROP.
- Use DuckDB date syntax (DATE_TRUNC, STRFTIME) for date operations.
- Always include LIMIT 500.
- Join tables when needed."""


def _history_block(history: list[dict] | None) -> str:
    """Render prior turns so the model can resolve follow-up references
    like "break that down by region" or "now just the top 3"."""
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


async def generate_sql(question: str, history: list[dict] | None = None) -> str:
    user_content = question + _history_block(history)
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:sql)?\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()