"""Regression tests for TossInvest edge/WAF response diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from alpha_cycle.providers.tossinvest import (
    HttpResponse,
    TossInvestCredentials,
    TossInvestReadOnlyClient,
    UrllibTransport,
)

NOW = datetime(2026, 7, 28, 4, 30, tzinfo=UTC)


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
        return self.responses.pop(0)


def test_non_json_response_includes_safe_http_diagnostics() -> None:
    with pytest.raises(ValueError) as captured:
        UrllibTransport._decode(
            b"<html><body>Request blocked by edge</body></html>",
            status=403,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "X-Request-Id": "request-123",
            },
        )
    message = str(captured.value)
    assert "status=403" in message
    assert "content_type=text/html" in message
    assert "request_id=request-123" in message
    assert "Request blocked by edge" in message


def test_auth_and_market_requests_send_explicit_json_headers() -> None:
    transport = FakeTransport(
        [
            HttpResponse(200, {}, {"access_token": "token", "expires_in": 3600}),
            HttpResponse(
                200,
                {},
                {
                    "result": [
                        {
                            "symbol": "005930",
                            "timestamp": "2026-07-28T13:30:00+09:00",
                            "lastPrice": "72000",
                            "currency": "KRW",
                        }
                    ]
                },
            ),
        ]
    )
    client = TossInvestReadOnlyClient(
        TossInvestCredentials("client", "secret"),
        transport=transport,
        now=lambda: NOW,
    )
    client.prices(["005930"])

    auth_headers = transport.requests[0][2]
    market_headers = transport.requests[1][2]
    assert auth_headers["Accept"] == "application/json"
    assert auth_headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert auth_headers["User-Agent"].startswith("Alpha-Cycle-Lab/")
    assert market_headers["Accept"] == "application/json"
    assert market_headers["Authorization"] == "Bearer token"
    assert market_headers["User-Agent"].startswith("Alpha-Cycle-Lab/")
