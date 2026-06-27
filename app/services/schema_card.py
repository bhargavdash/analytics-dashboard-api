"""Builds a grounded schema card: columns + real categorical values + few-shot.

Why: a bare column list lets the model guess `status = 'completed'` when the data
actually says 'shipped'. Feeding distinct values for low-cardinality columns (grounding)
sharply cuts wrong queries. Cached — introspection runs once per process.

In Phase B this becomes per-dataset; for now it reads the built-in warehouse.
"""

import duckdb
from functools import lru_cache

DB_PATH = "analytics.duckdb"

# Columns worth grounding with their actual values (low cardinality / enum-like).
_LOW_CARD_COLS = [
    ("orders", "region"),
    ("orders", "status"),
    ("products", "category"),
    ("customers", "segment"),
    ("customers", "country"),
    ("sales_reps", "team"),
]

_FEW_SHOT = """Example questions and the SQL they map to:
- "monthly revenue trend for 2026" ->
    SELECT date_trunc('month', order_date) AS month, SUM(amount) AS revenue
    FROM orders WHERE order_date >= '2026-01-01' GROUP BY 1 ORDER BY 1
- "top 5 customers by spend" ->
    SELECT c.name, SUM(o.amount) AS total_spend
    FROM orders o JOIN customers c ON o.customer_id = c.customer_id
    GROUP BY 1 ORDER BY total_spend DESC LIMIT 5"""


@lru_cache(maxsize=1)
def get_schema_card() -> str:
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        lines: list[str] = ["Tables:"]
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        for (t,) in tables:
            cols = con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [t],
            ).fetchall()
            coldesc = ", ".join(f"{c} {d}" for c, d in cols)
            lines.append(f"  {t}({coldesc})")

        lines.append("\nKnown categorical values (use these exact strings):")
        for tbl, col in _LOW_CARD_COLS:
            try:
                vals = con.execute(
                    f"SELECT DISTINCT {col} FROM {tbl} "
                    f"WHERE {col} IS NOT NULL ORDER BY 1 LIMIT 25"
                ).fetchall()
                rendered = ", ".join(str(v[0]) for v in vals)
                lines.append(f"  - {tbl}.{col}: {rendered}")
            except duckdb.Error:
                pass

        lines.append("\n" + _FEW_SHOT)
        return "\n".join(lines)
    finally:
        con.close()
