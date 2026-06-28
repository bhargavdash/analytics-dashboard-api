"""Type-coercion tests for db_exec._coerce.

DuckDB hands back decimal.Decimal and datetime objects that are not JSON-serializable;
_coerce normalizes them. This is the exact boundary that broke the SSE stream in
Sprint 4, so it gets explicit coverage.
"""

import datetime
from decimal import Decimal

from app.services.db_exec import _coerce


def test_decimal_becomes_float():
    out = _coerce(Decimal("3.14"))
    assert out == 3.14
    assert isinstance(out, float)


def test_date_becomes_iso_string():
    assert _coerce(datetime.date(2024, 1, 15)) == "2024-01-15"


def test_datetime_becomes_iso_string():
    out = _coerce(datetime.datetime(2024, 1, 15, 12, 0))
    assert out == "2024-01-15T12:00:00"
    assert isinstance(out, str)


def test_none_passes_through():
    assert _coerce(None) is None


def test_primitives_pass_through():
    assert _coerce("hello") == "hello"
    assert _coerce(42) == 42
    assert _coerce(True) is True


def test_mixed_row_coerces_correctly():
    row = [Decimal("9.99"), datetime.date(2024, 6, 1), "north", None, 7]
    coerced = [_coerce(v) for v in row]
    assert coerced == [9.99, "2024-06-01", "north", None, 7]
