"""SQL guardrails enforced at the boundary — not in the prompt.

A prompt rule ("SELECT only") is a suggestion; this is enforcement. Pairs with the
read_only DuckDB connection in db_exec (which is the real write-protection).
"""

import re

# Whole-word keywords that must never appear — DML/DDL and DuckDB side-effects.
_FORBIDDEN = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "ATTACH", "DETACH", "COPY", "PRAGMA", "INSTALL", "LOAD", "EXPORT",
    "IMPORT", "CALL", "REPLACE",
}


def validate_sql(sql: str) -> str:
    """Return a normalized single SELECT/WITH statement, or raise ValueError."""
    s = sql.strip().rstrip(";").strip()
    if not s:
        raise ValueError("empty query")

    # Reject multiple statements (the `SELECT ...; DROP ...` class).
    if ";" in s:
        raise ValueError("only a single statement is allowed")

    upper = s.upper()
    # Allow CTEs (WITH ...) — the old startswith('SELECT') check wrongly rejected them.
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("only SELECT/WITH queries are allowed")

    tokens = set(re.findall(r"[A-Za-z_]+", upper))
    bad = tokens & _FORBIDDEN
    if bad:
        raise ValueError(f"disallowed keyword(s): {', '.join(sorted(bad))}")

    return s


def enforce_limit(sql: str, cap: int = 500) -> str:
    """Guarantee a row cap even if the model forgot LIMIT."""
    if re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        return sql
    return f"{sql}\nLIMIT {cap}"
