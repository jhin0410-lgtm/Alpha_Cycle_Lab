"""Regression guard for the OpenDART stock-total history provider route."""

from alpha_cycle.opendart_stock_totals_history_cli import OpenDartValuationClient
from alpha_cycle.providers.opendart_valuation_resilient import (
    OpenDartValuationClient as ResilientOpenDartValuationClient,
)


def test_stock_totals_history_uses_resilient_share_count_boundary() -> None:
    assert OpenDartValuationClient is ResilientOpenDartValuationClient
