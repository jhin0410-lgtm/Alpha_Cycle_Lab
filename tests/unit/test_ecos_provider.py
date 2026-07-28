"""Tests for Bank of Korea ECOS read-only normalization."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from alpha_cycle.providers.ecos import (
    EcosCredentials,
    EcosReadOnlyClient,
    EcosSeriesSpec,
    load_ecos_series_config,
)
from alpha_cycle.providers.read_only_http import HttpBytesResponse

NOW = datetime(2026, 7, 28, 6, 30, tzinfo=UTC)


class FakeTransport:
    def __init__(self, responses: list[HttpBytesResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        assert timeout_seconds > 0
        assert isinstance(headers, Mapping)
        self.urls.append(url)
        return self.responses.pop(0)


def _response(payload: object) -> HttpBytesResponse:
    return HttpBytesResponse(200, {}, json.dumps(payload).encode())


def test_ecos_search_uses_conservative_retrieval_availability() -> None:
    transport = FakeTransport(
        [
            _response(
                {
                    "StatisticSearch": {
                        "row": [
                            {"TIME": "2026Q1", "DATA_VALUE": "1.2", "UNIT_NAME": "%"},
                            {"TIME": "2026Q2", "DATA_VALUE": "1.3", "UNIT_NAME": "%"},
                        ]
                    }
                }
            )
        ]
    )
    client = EcosReadOnlyClient(
        EcosCredentials("secret"),
        transport=transport,
        now=lambda: NOW,
    )
    frame, _ = client.search(
        EcosSeriesSpec(
            "kr_growth",
            "200Y001",
            "Q",
            "2026Q1",
            "2026Q2",
            ("10101",),
        )
    )
    assert frame["observation_date"].astype(str).tolist() == [
        "2026-01-01",
        "2026-04-01",
    ]
    assert set(frame["available_date"].astype(str)) == {"2026-07-28"}
    assert set(frame["source"]) == {"ecos"}


def test_ecos_error_does_not_expose_key() -> None:
    transport = FakeTransport(
        [
            _response(
                {
                    "RESULT": {
                        "CODE": "INFO-200",
                        "MESSAGE": "해당하는 데이터가 없습니다",
                    }
                }
            )
        ]
    )
    client = EcosReadOnlyClient(EcosCredentials("secret"), transport=transport)
    with pytest.raises(ValueError) as exc_info:
        client.search(EcosSeriesSpec("x", "code", "M", "202601", "202602"))
    assert "INFO-200" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


def test_ecos_config_requires_unique_series_ids(tmp_path) -> None:
    path = tmp_path / "ecos.yaml"
    path.write_text(
        "series:\n"
        "  - {series_id: x, stat_code: 1, cycle: M, start: '202601', end: '202602'}\n"
        "  - {series_id: x, stat_code: 2, cycle: M, start: '202601', end: '202602'}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unique"):
        load_ecos_series_config(path)


def test_ecos_credentials_and_cycle_validation() -> None:
    with pytest.raises(ValueError, match="must be set"):
        EcosCredentials.from_env({})
    with pytest.raises(ValueError, match="official"):
        EcosCredentials("secret", base_url="https://example.com")
    with pytest.raises(ValueError, match="cycle"):
        EcosSeriesSpec("x", "code", "W", "20260101", "20260131")
