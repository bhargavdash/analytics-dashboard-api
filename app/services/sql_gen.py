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


async def generate_sql(question: str) -> str:
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:sql)?\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()