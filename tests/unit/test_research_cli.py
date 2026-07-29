"""Tests for the OpenDART and ECOS research CLI."""

from __future__ import annotations

import pytest

from alpha_cycle.research_cli import _stock_codes


def test_stock_codes_preserve_and_restore_leading_zeroes() -> None:
    assert _stock_codes("005930,000660") == ["005930", "000660"]
    assert _stock_codes("5930,660") == ["005930", "000660"]


def test_stock_codes_deduplicate_after_normalization() -> None:
    assert _stock_codes("005930,5930") == ["005930"]


@pytest.mark.parametrize("value", ["", "AAPL", "1234567", "005930,AAPL"])
def test_stock_codes_reject_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        _stock_codes(value)
