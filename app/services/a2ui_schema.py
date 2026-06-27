import os
import json
from typing import AsyncIterator
from pydantic import ValidationError
from openai import AsyncOpenAI
from app.models.widgets import Widget, WidgetSchema, DataRow

MAX_RETRIES = 3

client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    timeout=30.0,
)

# Two concerns, two calls:
#   - stream_insight() → free-text prose, streamed token-by-token (the "alive" feel).
#   - generate_widgets() → structured chart spec, JSON mode, Pydantic-validated + retried.
# Splitting them lets the insight materialize word-by-word in the UI while the charts
# are still being assembled, instead of the whole answer popping in at once.

# The contract we give the LLM: widget types, exact field names, span rules, color palette.
# "Output ONLY valid JSON" is the most important line — models drift toward markdown wrapping.
WIDGET_SYSTEM_PROMPT = """You are a data visualization agent. Given a user question and SQL result rows, output a JSON object describing a dashboard.

Output schema:
{
  "widgets": [array of widget objects]
}

Available widget types:

stat_card   — span 3, synthesize a single headline number from the data
  { "type": "stat_card", "span": 3, "title": "...", "payload": { "value": "$3.2M", "delta": "+12%", "up": true, "vs": "vs last year" } }

line_chart  — span 8 or 12, trends over time
  { "type": "line_chart", "span": 8, "title": "...", "payload": { "data": [...rows], "xKey": "month", "series": [{"key": "revenue", "color": "oklch(0.72 0.17 290)", "label": "Revenue"}], "unit": "k" } }

bar_chart   — span 6 or 8, comparisons across categories
  { "type": "bar_chart", "span": 6, "title": "...", "payload": { "data": [...rows], "xKey": "category", "series": [{"key": "value", "color": "oklch(0.82 0.12 200)", "label": "Value"}] } }

pie_chart   — span 4, part-to-whole composition
  { "type": "pie_chart", "span": 4, "title": "...", "payload": { "slices": [{"name": "North", "value": 48, "color": "oklch(0.72 0.17 290)"}] } }

table       — span 12, detailed row data
  { "type": "table", "span": 12, "title": "...", "payload": { "data": [...rows], "columns": [{"key": "field", "label": "Display Name"}] } }

Rules:
- Spans in each row must sum to 12
- Always include at least one stat_card and one chart
- Use oklch colors only: oklch(0.72 0.17 290) purple · oklch(0.82 0.12 200) teal · oklch(0.78 0.16 150) green · oklch(0.82 0.14 75) amber · oklch(0.72 0.20 25) red
- For stat_cards: synthesize the value from the data — do not pass raw rows as payload
- Output ONLY valid JSON. No markdown fences, no explanation, no extra text."""


# Prose insight prompt. Kept deliberately terse — this streams, so every sentence should
# earn its place. We interpret the result, we do not narrate the chart.
INSIGHT_SYSTEM_PROMPT = """You are a senior data analyst. Given a user's question and the SQL result rows, write a tight 2-3 sentence interpretation for a business audience.

- Lead with the headline finding and the single most important number.
- Note one comparison, trend, or outlier if the data shows one.
- Plain prose only — no markdown, no bullet points, no headings.
- No preamble ("Based on the data…", "The results show…"). Start with the finding.
- Interpret the result; do not describe the chart."""


def _user_content(question: str, rows: list[DataRow]) -> str:
    return f"Question: {question}\n\nSQL rows:\n{json.dumps(rows, indent=2)}"


async def stream_insight(question: str, rows: list[DataRow]) -> AsyncIterator[str]:
    """Stream the prose interpretation token-by-token (free text, no JSON mode)."""
    stream = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
            {"role": "user", "content": _user_content(question, rows)},
        ],
        temperature=0.3,
        stream=True,
    )
    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token


async def generate_widgets(question: str, rows: list[DataRow]) -> list[Widget]:
    """Structured chart spec — JSON mode, validated against the widget union, with a repair loop."""
    user_content = _user_content(question, rows)
    error_feedback = ""

    for attempt in range(MAX_RETRIES):
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": WIDGET_SYSTEM_PROMPT},
                {"role": "user", "content": user_content + error_feedback},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        raw = response.choices[0].message.content

        try:
            data = json.loads(raw)
            return WidgetSchema.model_validate(data).widgets
        except (json.JSONDecodeError, ValidationError) as e:
            if attempt == MAX_RETRIES - 1:
                raise
            error_feedback = (
                f"\n\nYour previous response failed validation: {e}\n"
                "Fix it and output ONLY valid JSON."
            )

    return []  # unreachable; the loop either returns or raises
