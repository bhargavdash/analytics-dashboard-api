import os
import json
from openai import OpenAI
from app.models.widgets import DashboardSchema, DataRow

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

# The contract we give the LLM: widget types, exact field names, span rules, color palette.
# "Output ONLY valid JSON" is the most important line — models drift toward markdown wrapping.
SYSTEM_PROMPT = """You are a data visualization agent. Given a user question and SQL result rows, output a JSON object describing a dashboard.

Output schema:
{
  "summary": "2-3 sentence interpretation of the data for a business user",
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


async def generate_dashboard_schema(question: str, rows: list[DataRow]) -> DashboardSchema:
    response = client.chat.completions.create(
        model="anthropic/claude-haiku-4-5",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nSQL rows:\n{json.dumps(rows, indent=2)}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)
    # Pydantic validates and narrows — raises ValidationError if LLM emitted bad schema
    return DashboardSchema.model_validate(data)
