"""Tests for the read-only Kiwoom REST credential and OAuth boundary."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from alpha_cycle import kiwoom_readiness_cli as readiness
from alpha_cycle.providers.kiwoom_rest import (
    LIVE_BASE_URL,
    TOKEN_PATH,
    KiwoomHttpResponse,
    KiwoomRestAuthClient,
    KiwoomRestCredentials,
)


class RecordingTransport:
    def __init__(self, response: KiwoomHttpResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | object,
        body: bytes | None,
        timeout_seconds: float,
    ) -> KiwoomHttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


def test_credentials_load_utf8_bom_local_files_without_exposing_paths(
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "account_appkey.txt"
    secret_file = tmp_path / "account_appsecret.txt"
    key_file.write_text("\ufeffAPP-KEY\n", encoding="utf-8")
    secret_file.write_text("secretkey=APP-SECRET\n", encoding="utf-8")

    credentials = KiwoomRestCredentials.from_env(
        {
            "KIWOOM_REST_APP_KEY_FILE": str(key_file),
            "KIWOOM_REST_APP_SECRET_FILE": str(secret_file),
        }
    )

    assert credentials.app_key == "APP-KEY"
    assert credentials.app_secret == "APP-SECRET"
    assert credentials.source == "local_text_files"
    assert str(key_file) not in repr(credentials.source)


def test_credentials_reject_open_api_plus_binary() -> None:
    with pytest.raises(ValueError, match="Open API\+ installer"):
        KiwoomRestCredentials.from_env(
            {
                "KIWOOM_REST_APP_KEY_FILE": "C:/OpenAPI/setup.exe",
                "KIWOOM_REST_APP_SECRET_FILE": "C:/OpenAPI/secret.txt",
            }
        )


def test_authentication_uses_official_json_contract() -> None:
    transport = RecordingTransport(
        KiwoomHttpResponse(
            status=200,
            headers={},
            payload={
                "return_code": 0,
                "return_msg": "정상적으로 처리되었습니다",
                "token": "ACCESS-TOKEN",
                "token_type": "Bearer",
                "expires_dt": "20260804155600",
            },
        )
    )
    client = KiwoomRestAuthClient(
        KiwoomRestCredentials("APP-KEY", "APP-SECRET", "test"),
        transport=transport,
    )

    token = client.authenticate()

    assert token.token == "ACCESS-TOKEN"
    assert token.token_type == "Bearer"
    assert token.expires_at == datetime(2026, 8, 4, 15, 56)
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == f"{LIVE_BASE_URL}{TOKEN_PATH}"
    body = json.loads(bytes(call["body"]).decode("utf-8"))
    assert body == {
        "grant_type": "client_credentials",
        "appkey": "APP-KEY",
        "secretkey": "APP-SECRET",
    }


def test_authentication_error_never_contains_credentials() -> None:
    transport = RecordingTransport(
        KiwoomHttpResponse(
            status=401,
            headers={},
            payload={"return_code": 3, "return_msg": "인증 실패"},
        )
    )
    credentials = KiwoomRestCredentials("SENSITIVE-KEY", "SENSITIVE-SECRET", "test")

    with pytest.raises(ValueError) as captured:
        KiwoomRestAuthClient(credentials, transport=transport).authenticate()

    message = str(captured.value)
    assert "SENSITIVE-KEY" not in message
    assert "SENSITIVE-SECRET" not in message
    assert "인증 실패" in message


def test_auth_client_exposes_no_account_or_order_methods() -> None:
    client = KiwoomRestAuthClient(
        KiwoomRestCredentials("APP-KEY", "APP-SECRET", "test")
    )

    assert not hasattr(client, "account")
    assert not hasattr(client, "balance")
    assert not hasattr(client, "order")
    assert not hasattr(client, "place_order")


def test_offline_readiness_writes_secret_free_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    key_file = tmp_path / "sensitive-account_appkey.txt"
    secret_file = tmp_path / "sensitive-account_appsecret.txt"
    key_file.write_text("APP-KEY", encoding="utf-8")
    secret_file.write_text("APP-SECRET", encoding="utf-8")
    monkeypatch.setenv("KIWOOM_REST_APP_KEY_FILE", str(key_file))
    monkeypatch.setenv("KIWOOM_REST_APP_SECRET_FILE", str(secret_file))
    output = tmp_path / "readiness.json"

    result = readiness.main(["--offline", "--output", str(output)])

    assert result == 0
    printed = capsys.readouterr().out
    artifact = output.read_text(encoding="utf-8")
    assert "KIWOOM REST READINESS: PASS" in printed
    for sensitive in (
        "APP-KEY",
        "APP-SECRET",
        str(key_file),
        str(secret_file),
        key_file.name,
        secret_file.name,
    ):
        assert sensitive not in printed
        assert sensitive not in artifact
    payload = json.loads(artifact)
    assert payload["order_api_enabled"] is False
    assert payload["account_api_enabled"] is False
    assert payload["authentication_attempted"] is False


def test_windows_setup_persists_paths_not_credential_contents() -> None:
    script = Path("scripts/setup_kiwoom_rest.ps1").read_text(encoding="utf-8")

    assert "KIWOOM_REST_APP_KEY_FILE" in script
    assert "KIWOOM_REST_APP_SECRET_FILE" in script
    assert "KIWOOM_REST_APP_KEY\"" not in script
    assert "KIWOOM_REST_APP_SECRET\"" not in script
    assert "Get-Content" not in script
