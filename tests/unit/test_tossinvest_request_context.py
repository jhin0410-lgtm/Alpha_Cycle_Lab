"""Regression tests for safe TossInvest request diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from alpha_cycle.providers import TossInvestCredentials, TossInvestReadOnlyClient
from alpha_cycle.providers.tossinvest import HttpResponse

NOW = datetime(2026, 7, 28, 5, 30, tzinfo=UTC)


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        assert method in {"GET", "POST"}
        assert url.startswith("https://openapi.tossinvest.com")
        assert timeout_seconds > 0
        assert headers
        _ = body
        if not self.responses:
            raise AssertionError("No fake response remains")
        return self.responses.pop(0)


def _token() -> HttpResponse:
    return HttpResponse(
        200,
        {},
        {"access_token": "secret-token-value", "expires_in": 3600},
    )


def _price(symbol: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timestamp": "2026-07-28T14:30:00+09:00",
        "lastPrice": "72000",
        "currency": "KRW",
    }


def _client(responses: list[HttpResponse]) -> TossInvestReadOnlyClient:
    return TossInvestReadOnlyClient(
        TossInvestCredentials("client", "secret"),
        transport=FakeTransport(responses),
        now=lambda: NOW,
    )


def test_failed_single_symbol_price_fallback_names_symbol_and_endpoint() -> None:
    client = _client(
        [
            _token(),
            HttpResponse(200, {}, {"result": [_price("005930")]}),
            HttpResponse(
                404,
                {},
                {
                    "error": {
                        "code": "stock-not-found",
                        "message": "종목을 찾을 수 없습니다.",
                        "requestId": "request-price-404",
                    }
                },
            ),
        ]
    )

    with pytest.raises(ValueError) as exc_info:
        client.prices(["005930", "000660"])

    message = str(exc_info.value)
    assert "single-symbol price fallback failed" in message
    assert "symbol=000660" in message
    assert "endpoint=/api/v1/prices" in message
    assert "query=symbols=000660" in message
    assert "request-price-404" in message
    assert "secret-token-value" not in message


def test_failed_candle_request_names_symbol_interval_and_endpoint() -> None:
    client = _client(
        [
            _token(),
            HttpResponse(
                404,
                {},
                {
                    "error": {
                        "code": "stock-not-found",
                        "message": "종목을 찾을 수 없습니다.",
                        "requestId": "request-candle-404",
                    }
                },
            ),
        ]
    )

    with pytest.raises(ValueError) as exc_info:
        client.candles("000660", interval="1d", count=100, adjusted=False)

    message = str(exc_info.value)
    assert "candle collection failed" in message
    assert "symbol=000660" in message
    assert "interval=1d" in message
    assert "count=100" in message
    assert "adjusted=false" in message
    assert "endpoint=/api/v1/candles" in message
    assert "query=symbol=000660,interval=1d,count=100,adjusted=false" in message
    assert "request-candle-404" in message
    assert "secret-token-value" not in message
