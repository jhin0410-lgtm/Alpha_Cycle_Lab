"""Tests for the semantically-unclassified KIS estimate-perform provider."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.providers.kis_research import (
    KIS_ESTIMATE_PERFORM_ENDPOINT,
    KIS_ESTIMATE_PERFORM_TR_ID,
    KIS_RESEARCH_SOURCE_SCOPE,
    KisResearchCredentials,
    KisResearchReadOnlyClient,
)
from alpha_cycle.providers.read_only_http import HttpBytesResponse

NOW = datetime(2026, 8, 7, 21, 0, tzinfo=ZoneInfo("Asia/Seoul"))


class FakeKisTransport:
    def __init__(self, research_payload: Mapping[str, object]) -> None:
        self.research_payload = dict(research_payload)
        self.posts: list[tuple[str, Mapping[str, str], bytes]] = []
        self.gets: list[tuple[str, Mapping[str, str]]] = []

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        assert timeout_seconds > 0
        self.posts.append((url, dict(headers), body))
        payload = {
            "access_token": "test-token",
            "access_token_token_expired": "2026-08-08 21:00:00",
        }
        return HttpBytesResponse(200, {}, json.dumps(payload).encode())

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        assert timeout_seconds > 0
        self.gets.append((url, dict(headers)))
        return HttpBytesResponse(200, {}, json.dumps(self.research_payload).encode())


def _payload() -> dict[str, object]:
    return {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리 되었습니다.",
        "output1": {"sht_cd": "005930", "item_kor_nm": "삼성전자"},
        "output2": [
            {"data1": "매출액", "data2": "100", "data3": "110", "data4": "120", "data5": "130"}
        ],
        "output3": [
            {"data1": "EPS", "data2": "10", "data3": "11", "data4": "12", "data5": "13"}
        ],
        "output4": [
            {"dt": "202412"},
            {"dt": "202512"},
            {"dt": "202612E"},
            {"dt": "202712E"},
        ],
    }


def test_estimate_perform_uses_only_research_endpoint_and_reuses_token() -> None:
    transport = FakeKisTransport(_payload())
    client = KisResearchReadOnlyClient(
        KisResearchCredentials("app-key", "app-secret"),
        transport=transport,
        now=lambda: NOW,
        sleep=lambda _: None,
    )

    first = client.estimate_perform("005930")
    second = client.estimate_perform("000660")

    assert first.symbol == "005930"
    assert second.symbol == "000660"
    assert first.endpoint == KIS_ESTIMATE_PERFORM_ENDPOINT
    assert first.tr_id == KIS_ESTIMATE_PERFORM_TR_ID
    assert first.source_scope == KIS_RESEARCH_SOURCE_SCOPE
    assert len(first.raw_response_sha256) == 64
    assert len(transport.posts) == 1
    assert len(transport.gets) == 2
    assert all(KIS_ESTIMATE_PERFORM_ENDPOINT in url for url, _ in transport.gets)
    assert "SHT_CD=005930" in transport.gets[0][0]
    assert transport.gets[0][1]["tr_id"] == KIS_ESTIMATE_PERFORM_TR_ID
    assert transport.gets[0][1]["Authorization"] == "Bearer test-token"
    assert not any(
        token in key.casefold()
        for _, headers in transport.gets
        for key in headers
        for token in ("account", "cano", "acnt")
    )


def test_oauth_payload_contains_app_credentials_but_no_account_identifier() -> None:
    transport = FakeKisTransport(_payload())
    client = KisResearchReadOnlyClient(
        KisResearchCredentials("app-key", "app-secret"),
        transport=transport,
        now=lambda: NOW,
        sleep=lambda _: None,
    )

    client.estimate_perform("005930")

    assert len(transport.posts) == 1
    _, _, body = transport.posts[0]
    payload = json.loads(body.decode())
    assert payload == {
        "grant_type": "client_credentials",
        "appkey": "app-key",
        "appsecret": "app-secret",
    }
    assert "account" not in body.decode().casefold()
    assert "cano" not in body.decode().casefold()


def test_provider_fails_closed_on_api_error() -> None:
    payload = _payload()
    payload.update({"rt_cd": "1", "msg_cd": "ERR001", "msg1": "조회 불가"})
    transport = FakeKisTransport(payload)
    client = KisResearchReadOnlyClient(
        KisResearchCredentials("app-key", "app-secret"),
        transport=transport,
        now=lambda: NOW,
        sleep=lambda _: None,
    )

    with pytest.raises(ValueError, match="ERR001"):
        client.estimate_perform("005930")


def test_credentials_do_not_require_account_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIS_APP_KEY", "app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "app-secret")
    monkeypatch.delenv("KIS_ACCOUNT_NUMBER", raising=False)

    credentials = KisResearchCredentials.from_env()

    assert credentials.app_key == "app-key"
    assert credentials.app_secret == "app-secret"
