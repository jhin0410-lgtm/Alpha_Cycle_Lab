"""Tests for resilient multi-symbol TossInvest price collection."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from alpha_cycle.providers import TossInvestCredentials, TossInvestReadOnlyClient
from alpha_cycle.providers.tossinvest import HttpResponse

NOW = datetime(2026, 7, 28, 5, 0, tzinfo=UTC)


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, Mapping[str, str], bytes | None]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        assert timeout_seconds > 0
        self.requests.append((method, url, headers, body))
        if not self.responses:
            raise AssertionError("No fake response remains")
        return self.responses.pop(0)


def _token() -> HttpResponse:
    return HttpResponse(
        200,
        {},
        {"access_token": "secret-token-value", "expires_in": 3600},
    )


def _price(symbol: object, price: str = "72000") -> dict[str, object]:
    return {
        "symbol": symbol,
        "timestamp": "2026-07-28T14:00:00+09:00",
        "lastPrice": price,
        "currency": "KRW",
    }


def _client(transport: FakeTransport) -> TossInvestReadOnlyClient:
    return TossInvestReadOnlyClient(
        TossInvestCredentials("client", "secret"),
        transport=transport,
        now=lambda: NOW,
    )


def test_partial_bulk_response_is_completed_with_single_symbol_fallback() -> None:
    transport = FakeTransport(
        [
            _token(),
            HttpResponse(
                200,
                {"X-RateLimit-Remaining": "9"},
                {"result": [_price("005930")]},
            ),
            HttpResponse(
                200,
                {"X-RateLimit-Remaining": "8"},
                {"result": [_price("000660", "300000")]},
            ),
        ]
    )

    batch = _client(transport).prices(["005930", "000660"])

    assert [item.symbol for item in batch.prices] == ["000660", "005930"]
    fallback_count = batch.response_headers["X-Alpha-Cycle-Price-Fallback-Count"]
    fallback_symbols = batch.response_headers[
        "X-Alpha-Cycle-Price-Fallback-Symbols"
    ]
    assert fallback_count == "1"
    assert fallback_symbols == "000660"
    assert isinstance(batch.raw_payload, dict)
    assert "symbols=005930%2C000660" in transport.requests[1][1]
    assert transport.requests[2][1].endswith("symbols=000660")


def test_numeric_response_symbols_restore_krx_leading_zeroes() -> None:
    transport = FakeTransport(
        [
            _token(),
            HttpResponse(
                200,
                {},
                {"result": [_price(5930), _price(660, "300000")]},
            ),
        ]
    )

    batch = _client(transport).prices(["005930", "000660"])

    assert [item.symbol for item in batch.prices] == ["000660", "005930"]
    assert len(transport.requests) == 2


def test_unexpected_bulk_symbol_is_rejected_without_fallback() -> None:
    transport = FakeTransport(
        [
            _token(),
            HttpResponse(
                200,
                {},
                {"result": [_price("005930"), _price("AAPL", "200")]},
            ),
        ]
    )

    with pytest.raises(ValueError, match="unexpected symbols") as exc_info:
        _client(transport).prices(["005930", "000660"])

    assert "AAPL" in str(exc_info.value)
    assert "000660" in str(exc_info.value)
    assert len(transport.requests) == 2


def test_too_many_missing_symbols_fail_closed_without_request_burst() -> None:
    symbols = [f"{index:06d}" for index in range(1, 12)]
    transport = FakeTransport([_token(), HttpResponse(200, {}, {"result": []})])

    with pytest.raises(ValueError, match="omitted too many symbols"):
        _client(transport).prices(symbols)

    assert len(transport.requests) == 2


def test_single_symbol_fallback_must_return_exact_requested_symbol() -> None:
    transport = FakeTransport(
        [
            _token(),
            HttpResponse(200, {}, {"result": [_price("005930")]}),
            HttpResponse(200, {}, {"result": []}),
        ]
    )

    with pytest.raises(
        ValueError,
        match="single-symbol fallback did not match",
    ) as exc_info:
        _client(transport).prices(["005930", "000660"])

    assert "missing=['000660']" in str(exc_info.value)
