"""SQL guardrail tests — boundary enforcement, not prompt suggestions."""

import pytest

from app.services.sql_safety import validate_sql, enforce_limit


def test_valid_select_passes():
    assert validate_sql("SELECT 1") == "SELECT 1"


def test_valid_select_from_table_passes():
    sql = "SELECT region, SUM(amount) FROM orders GROUP BY region"
    assert validate_sql(sql) == sql


def test_cte_with_passes():
    sql = "WITH t AS (SELECT 1 AS x) SELECT x FROM t"
    assert validate_sql(sql) == sql


def test_trailing_semicolon_is_stripped():
    assert validate_sql("SELECT 1;") == "SELECT 1"


def test_multi_statement_is_rejected():
    with pytest.raises(ValueError):
        validate_sql("SELECT 1; SELECT 2")


def test_select_then_drop_is_rejected():
    with pytest.raises(ValueError):
        validate_sql("SELECT * FROM orders; DROP TABLE orders")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders VALUES (1)",
        "UPDATE orders SET amount = 0",
        "DELETE FROM orders",
        "DROP TABLE orders",
    ],
)
def test_dml_ddl_is_rejected(sql):
    with pytest.raises(ValueError):
        validate_sql(sql)


def test_forbidden_keyword_inside_allowed_prefix_is_rejected():
    # Starts with WITH (allowed prefix) but smuggles a DELETE — the keyword allowlist
    # must still catch it.
    with pytest.raises(ValueError):
        validate_sql("WITH t AS (SELECT 1) DELETE FROM t")


def test_empty_query_is_rejected():
    with pytest.raises(ValueError):
        validate_sql("   ")


def test_validate_does_not_inject_limit():
    # Per the current impl, validate_sql neither requires nor injects a LIMIT.
    assert "LIMIT" not in validate_sql("SELECT 1").upper()


def test_enforce_limit_injects_when_missing():
    out = enforce_limit("SELECT 1", cap=500)
    assert out == "SELECT 1\nLIMIT 500"


def test_enforce_limit_respects_existing_limit():
    sql = "SELECT 1 LIMIT 10"
    assert enforce_limit(sql, cap=500) == sql
