"""Builds a grounded schema card: columns + real categorical values + few-shot.

Why: a bare column list lets the model guess `status = 'completed'` when the data
actually says 'shipped'. Feeding distinct values for low-cardinality columns (grounding)
sharply cuts wrong queries. Cached — introspection runs once per table per process.

Phase B: the card is now per-dataset. `resolve_schema_card(dataset)` returns the demo
warehouse card when dataset is None, else a card for that uploaded table. The orchestrator
picks which and injects it into the router + SQL generator (no longer a global import).
"""

import duckdb
from functools import lru_cache
from app.db.connection import WAREHOUSE_DB_PATH, DATASETS_DB_PATH

# Demo warehouse: columns worth grounding with their actual values (enum-like).
_LOW_CARD_COLS = [
    ("orders", "region"),
    ("orders", "status"),
    ("products", "category"),
    ("customers", "segment"),
    ("customers", "country"),
    ("sales_reps", "team"),
]

_DEMO_FEW_SHOT = """Example questions and the SQL they map to:
- "monthly revenue trend for 2026" ->
    SELECT date_trunc('month', order_date) AS month, SUM(amount) AS revenue
    FROM orders WHERE order_date >= '2026-01-01' GROUP BY 1 ORDER BY 1
- "top 5 customers by spend" ->
    SELECT c.name, SUM(o.amount) AS total_spend
    FROM orders o JOIN customers c ON o.customer_id = c.customer_id
    GROUP BY 1 ORDER BY total_spend DESC LIMIT 5"""

# How many distinct values still counts as "categorical" (worth listing for grounding).
_MAX_CARDINALITY = 25


@lru_cache(maxsize=1)
def get_demo_schema_card() -> str:
    con = duckdb.connect(str(WAREHOUSE_DB_PATH), read_only=True)
    try:
        lines: list[str] = ["Tables:"]
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name NOT LIKE 'ds_%' ORDER BY table_name"
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

        lines.append("\n" + _DEMO_FEW_SHOT)
        return "\n".join(lines)
    finally:
        con.close()


@lru_cache(maxsize=64)
def build_dataset_schema_card(table_name: str) -> str:
    """A grounded card for one uploaded table: columns, dynamically-detected
    categorical values, and a couple of real sample rows. Cached per table (datasets
    are immutable once ingested)."""
    con = duckdb.connect(str(DATASETS_DB_PATH), read_only=True)
    try:
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table_name],
        ).fetchall()
        if not cols:
            raise ValueError(f"unknown dataset table: {table_name}")

        coldesc = ", ".join(f"{c} {d}" for c, d in cols)
        lines: list[str] = ["Table (this is the ONLY table — query it directly):"]
        lines.append(f'  "{table_name}"({coldesc})')

        # Detect low-cardinality text columns and list their actual values.
        cat_lines: list[str] = []
        for col, dtype in cols:
            if "VARCHAR" not in dtype.upper() and "CHAR" not in dtype.upper():
                continue
            try:
                n = con.execute(
                    f'SELECT COUNT(DISTINCT "{col}") FROM "{table_name}"'
                ).fetchone()[0]
                if 0 < n <= _MAX_CARDINALITY:
                    vals = con.execute(
                        f'SELECT DISTINCT "{col}" FROM "{table_name}" '
                        f'WHERE "{col}" IS NOT NULL ORDER BY 1 LIMIT {_MAX_CARDINALITY}'
                    ).fetchall()
                    rendered = ", ".join(str(v[0]) for v in vals)
                    cat_lines.append(f"  - {col}: {rendered}")
            except duckdb.Error:
                pass
        if cat_lines:
            lines.append("\nKnown categorical values (use these exact strings):")
            lines.extend(cat_lines)

        # A few sample rows ground the model in the real shape of the data.
        try:
            sample = con.execute(
                f'SELECT * FROM "{table_name}" LIMIT 3'
            ).fetchall()
            names = [c for c, _ in cols]
            lines.append("\nSample rows:")
            for row in sample:
                rendered = ", ".join(f"{k}={v}" for k, v in zip(names, row))
                lines.append(f"  - {rendered}")
        except duckdb.Error:
            pass

        return "\n".join(lines)
    finally:
        con.close()


def resolve_schema_card(dataset: dict | None) -> str:
    """Pick the right schema card: demo warehouse (None) or an uploaded table."""
    if dataset is None:
        return get_demo_schema_card()
    return build_dataset_schema_card(dataset["table_name"])
