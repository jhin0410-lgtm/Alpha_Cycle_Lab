"""Tests for the read-only TossInvest market-data boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Mapping

import pytest

from alpha_cycle.providers.tossinvest import (
    HttpResponse,
    TossInvestCredentials,
    TossInvestReadOnlyClient,
)

NOW = datetime(2026, 7, 28, 3, 30, tzinfo=UTC)


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


def test_credentials_are_loaded_only_from_non_placeholder_environment() -> None:
    with pytest.raises(ValueError, match="must be set"):
        TossInvestCredentials.from_env({})
    with pytest.raises(ValueError, match="placeholder"):
        TossInvestCredentials.from_env(
            {
                "TOSSINVEST_CLIENT_ID": "replace_with_local_secret",
                "TOSSINVEST_CLIENT_SECRET": "secret",
            }
        )
    credentials = TossInvestCredentials.from_env(
        {
            "TOSSINVEST_CLIENT_ID": "client",
            "TOSSINVEST_CLIENT_SECRET": "secret",
        }
    )
    assert credentials.client_id == "client"


def test_prices_and_candles_parse_with_one_cached_token() -> None:
    transport = FakeTransport(
        [
            _token(),
            HttpResponse(
                200,
                {"X-RateLimit-Remaining": "9"},
                {
                    "result": [
                        {
                            "symbol": "005930",
                            "timestamp": "2026-07-28T12:30:00+09:00",
                            "lastPrice": "72000",
                            "currency": "KRW",
                        }
                    ]
                },
            ),
            HttpResponse(
                200,
                {"X-RateLimit-Remaining": "4"},
                {
                    "result": {
                        "candles": [
                            {
                                "timestamp": "2026-07-28T12:29:00+09:00",
                                "openPrice": "71900",
                                "highPrice": "72100",
                                "lowPrice": "71800",
                                "closePrice": "72000",
                                "volume": "1000",
                                "currency": "KRW",
                            }
                        ],
                        "nextBefore": None,
                    }
                },
            ),
        ]
    )
    client = TossInvestReadOnlyClient(
        TossInvestCredentials("client", "secret"),
        transport=transport,
        now=lambda: NOW,
    )
    prices = client.prices(["005930"])
    candles = client.candles("005930", interval="1m", count=1, adjusted=False)
    assert prices.prices[0].last_price == 72000
    assert candles.candles[0].adjusted is False
    assert candles.candles[0].close_price == 72000
    assert len([request for request in transport.requests if request[0] == "POST"]) == 1
    assert all("secret-token-value" not in request[1] for request in transport.requests)
    assert "adjusted=false" in transport.requests[-1][1]


def test_rate_limit_retry_honors_retry_after() -> None:
    delays: list[float] = []
    transport = FakeTransport(
        [
            _token(),
            HttpResponse(429, {"Retry-After": "2"}, {"error": {"code": "rate-limit"}}),
            HttpResponse(
                200,
                {},
                {
                    "result": [
                        {
                            "symbol": "AAPL",
                            "timestamp": "2026-07-28T03:30:00+00:00",
                            "lastPrice": "200",
                            "currency": "USD",
                        }
                    ]
                },
            ),
        ]
    )
    client = TossInvestReadOnlyClient(
        TossInvestCredentials("client", "secret"),
        transport=transport,
        sleep=delays.append,
        now=lambda: NOW,
    )
    assert client.prices(["AAPL"]).prices[0].symbol == "AAPL"
    assert delays == [2.0]


def test_read_only_allow_list_blocks_order_paths() -> None:
    client = TossInvestReadOnlyClient(
        TossInvestCredentials("client", "secret"),
        transport=FakeTransport([]),
        now=lambda: NOW,
    )
    with pytest.raises(ValueError, match="read-only allow-list"):
        client._authorized_get("/api/v1/orders", {})


def test_input_limits_are_explicit() -> None:
    client = TossInvestReadOnlyClient(
        TossInvestCredentials("client", "secret"),
        transport=FakeTransport([]),
        now=lambda: NOW,
    )
    with pytest.raises(ValueError, match="at most 200"):
        client.prices([f"S{index}" for index in range(201)])
    with pytest.raises(ValueError, match="between 1 and 200"):
        client.candles("005930", interval="1d", count=201)
    with pytest.raises(ValueError, match="1m or 1d"):
        client.candles("005930", interval="5m", count=10)
