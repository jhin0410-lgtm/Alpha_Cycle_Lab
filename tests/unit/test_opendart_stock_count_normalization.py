"""Regression tests for real-world OpenDART whole-share count formats."""

from __future__ import annotations

import pytest

from alpha_cycle.providers.opendart_valuation import _integer


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1,234", 1234),
        (" 1 234 ", 1234),
        ("1,234주", 1234),
        ("0.0", 0),
        ("1,234.000", 1234),
        (0, 0),
    ],
)
def test_integer_accepts_unambiguous_whole_share_formats(
    value: object,
    expected: int,
) -> None:
    assert _integer(value, "count") == expected


@pytest.mark.parametrize(
    "value",
    [None, "", "-", "–", "—", "−", "해당사항 없음", "N/A", "null"],
)
def test_integer_accepts_source_missing_markers_for_optional_fields(value: object) -> None:
    assert _integer(value, "count") is None


@pytest.mark.parametrize("value", ["0.5", "1e3", "12주식", "unknown", "(100)", "-1"])
def test_integer_rejects_ambiguous_or_negative_share_counts(value: object) -> None:
    with pytest.raises(ValueError, match="whole-share count"):
        _integer(value, "count")


def test_required_integer_rejects_missing_source_value() -> None:
    with pytest.raises(ValueError, match="is required"):
        _integer("-", "count", optional=False)


def test_invalid_integer_error_includes_sanitized_source_value() -> None:
    with pytest.raises(ValueError, match="value='unknown'"):
        _integer("unknown", "count")
