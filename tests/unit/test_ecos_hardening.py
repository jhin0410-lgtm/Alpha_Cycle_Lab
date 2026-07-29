"""Regression tests for ECOS validation and Korea-date availability."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from alpha_cycle.providers.ecos import (
    EcosCredentials,
    EcosReadOnlyClient,
    EcosSeriesSpec,
)
from alpha_cycle.providers.read_only_http import HttpBytesResponse


class FakeTransport:
    def __init__(self, responses: list[HttpBytesResponse]) -> None:
        self.responses = responses

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        assert url.startswith("https://ecos.bok.or.kr/api/")
        assert isinstance(headers, Mapping)
        assert timeout_seconds > 0
        return self.responses.pop(0)


def _response(payload: object) -> HttpBytesResponse:
    return HttpBytesResponse(200, {}, json.dumps(payload).encode())


def test_series_spec_validates_period_order() -> None:
    with pytest.raises(ValueError, match="start cannot follow end"):
        EcosSeriesSpec("x", "code", "M", "202602", "202601")


def test_availability_uses_korea_date_and_skips_missing_values() -> None:
    client = EcosReadOnlyClient(
        EcosCredentials("secret"),
        transport=FakeTransport(
            [
                _response(
                    {
                        "StatisticSearch": {
                            "list_total_count": 2,
                            "row": [
                                {
                                    "STAT_CODE": "722Y001",
                                    "ITEM_CODE1": "0101000",
                                    "TIME": "20260728",
                                    "DATA_VALUE": "-",
                                    "UNIT_NAME": "%",
                                },
                                {
                                    "STAT_CODE": "722Y001",
                                    "ITEM_CODE1": "0101000",
                                    "TIME": "20260729",
                                    "DATA_VALUE": "2.50",
                                    "UNIT_NAME": "%",
                                },
                            ],
                        }
                    }
                )
            ]
        ),
        now=lambda: datetime(2026, 7, 28, 16, 30, tzinfo=UTC),
    )

    frame, _ = client.search(
        EcosSeriesSpec(
            "kr_base_rate",
            "722Y001",
            "D",
            "20260728",
            "20260729",
            ("0101000",),
        )
    )

    assert frame["observation_date"].astype(str).tolist() == ["2026-07-29"]
    assert frame["available_date"].astype(str).tolist() == ["2026-07-29"]


def test_truncated_response_fails_instead_of_silently_dropping_rows() -> None:
    client = EcosReadOnlyClient(
        EcosCredentials("secret"),
        transport=FakeTransport(
            [
                _response(
                    {
                        "StatisticSearch": {
                            "list_total_count": 2,
                            "row": [
                                {
                                    "TIME": "20260728",
                                    "DATA_VALUE": "2.5",
                                    "UNIT_NAME": "%",
                                }
                            ],
                        }
                    }
                )
            ]
        ),
    )

    with pytest.raises(ValueError, match="truncated"):
        client.search(
            EcosSeriesSpec("kr_base_rate", "722Y001", "D", "20260728", "20260729")
        )


def test_response_identity_mismatch_fails_closed() -> None:
    client = EcosReadOnlyClient(
        EcosCredentials("secret"),
        transport=FakeTransport(
            [
                _response(
                    {
                        "StatisticSearch": {
                            "row": [
                                {
                                    "STAT_CODE": "WRONG",
                                    "TIME": "20260728",
                                    "DATA_VALUE": "2.5",
                                }
                            ]
                        }
                    }
                )
            ]
        ),
    )

    with pytest.raises(ValueError, match="STAT_CODE"):
        client.search(
            EcosSeriesSpec("kr_base_rate", "722Y001", "D", "20260728", "20260728")
        )


def test_duplicate_time_requires_more_specific_item_codes() -> None:
    client = EcosReadOnlyClient(
        EcosCredentials("secret"),
        transport=FakeTransport(
            [
                _response(
                    {
                        "StatisticSearch": {
                            "row": [
                                {"TIME": "20260728", "DATA_VALUE": "2.5"},
                                {"TIME": "20260728", "DATA_VALUE": "3.0"},
                            ]
                        }
                    }
                )
            ]
        ),
    )

    with pytest.raises(ValueError, match="item_codes"):
        client.search(EcosSeriesSpec("x", "code", "D", "20260728", "20260728"))
