"""Regression tests for adjusted daily market evidence in the live pipeline."""

from __future__ import annotations

import ast
import inspect
from types import MethodType

from alpha_cycle import live_pipeline_cli as live
from alpha_cycle.providers.tossinvest import (
    HttpResponse,
    TossInvestCredentials,
    TossInvestReadOnlyClient,
)


def test_live_pipeline_requests_adjusted_daily_market_data() -> None:
    tree = ast.parse(inspect.getsource(live._execute))
    adjusted_keywords = [
        keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "adjusted"
    ]

    assert len(adjusted_keywords) == 1
    assert isinstance(adjusted_keywords[0], ast.Constant)
    assert adjusted_keywords[0].value is True


def test_toss_daily_candle_request_preserves_adjusted_true() -> None:
    client = TossInvestReadOnlyClient(
        TossInvestCredentials(client_id="test-id", client_secret="test-secret")
    )
    captured: dict[str, object] = {}

    def authorized_get(
        self: TossInvestReadOnlyClient,
        path: str,
        query: dict[str, str],
    ) -> HttpResponse:
        captured["path"] = path
        captured["query"] = dict(query)
        return HttpResponse(
            status=200,
            headers={},
            payload={
                "result": {
                    "candles": [
                        {
                            "timestamp": "2026-08-07T15:30:00+09:00",
                            "openPrice": "100",
                            "highPrice": "110",
                            "lowPrice": "95",
                            "closePrice": "105",
                            "volume": "1000",
                            "currency": "KRW",
                        }
                    ],
                    "nextBefore": None,
                }
            },
        )

    client._authorized_get = MethodType(authorized_get, client)  # type: ignore[method-assign]
    batch = client.candles(
        "005930",
        interval="1d",
        count=1,
        adjusted=True,
    )

    assert captured["path"] == "/api/v1/candles"
    assert captured["query"] == {
        "symbol": "005930",
        "interval": "1d",
        "count": "1",
        "adjusted": "true",
    }
    assert len(batch.candles) == 1
    assert batch.candles[0].adjusted is True
