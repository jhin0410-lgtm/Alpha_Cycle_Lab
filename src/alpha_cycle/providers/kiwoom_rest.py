"""Minimal official-host-only Kiwoom REST authentication boundary.

This module intentionally exposes authentication readiness only. Account, holding,
and order endpoints are not implemented.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from email.message import Message
from http.client import HTTPMessage
from pathlib import Path
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LIVE_BASE_URL = "https://api.kiwoom.com"
MOCK_BASE_URL = "https://mockapi.kiwoom.com"
TOKEN_PATH = "/oauth2/token"
_ALLOWED_BASE_URLS = frozenset({LIVE_BASE_URL, MOCK_BASE_URL})
_UNSUPPORTED_SECRET_FILE_SUFFIXES = frozenset(
    {".exe", ".msi", ".dll", ".ocx", ".zip", ".7z", ".rar"}
)


@dataclass(frozen=True)
class KiwoomRestCredentials:
    """Credentials loaded from direct environment values or local text files."""

    app_key: str
    app_secret: str
    source: str

    @staticmethod
    def _validate_secret(value: str, name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} is blank")
        if "replace_with" in normalized.casefold():
            raise ValueError(f"{name} is a placeholder")
        if any(character in normalized for character in "\r\n\x00"):
            raise ValueError(f"{name} must be a single text value")
        return normalized

    @classmethod
    def _read_secret_file(cls, raw_path: str, name: str) -> str:
        path = Path(raw_path).expanduser()
        if path.suffix.casefold() in _UNSUPPORTED_SECRET_FILE_SUFFIXES:
            raise ValueError(
                f"{name} must reference the Kiwoom REST text credential, "
                "not an Open API+ installer or binary"
            )
        if not path.is_file():
            raise ValueError(f"{name} file does not exist")
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{name} file must be UTF-8 text") from exc
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if len(lines) != 1:
            raise ValueError(f"{name} file must contain exactly one non-empty line")
        line = lines[0]
        if "=" in line:
            _, line = line.split("=", 1)
        elif ":" in line:
            label, candidate = line.split(":", 1)
            if "key" in label.casefold() or "secret" in label.casefold():
                line = candidate
        return cls._validate_secret(line, name)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> KiwoomRestCredentials:
        values = os.environ if environ is None else environ
        app_key = values.get("KIWOOM_REST_APP_KEY", "").strip()
        app_secret = values.get("KIWOOM_REST_APP_SECRET", "").strip()
        key_file = values.get("KIWOOM_REST_APP_KEY_FILE", "").strip()
        secret_file = values.get("KIWOOM_REST_APP_SECRET_FILE", "").strip()

        if app_key or app_secret:
            if not app_key or not app_secret:
                raise ValueError(
                    "KIWOOM_REST_APP_KEY and KIWOOM_REST_APP_SECRET must be set together"
                )
            return cls(
                app_key=cls._validate_secret(app_key, "Kiwoom REST App Key"),
                app_secret=cls._validate_secret(
                    app_secret,
                    "Kiwoom REST App Secret",
                ),
                source="environment_values",
            )

        if key_file or secret_file:
            if not key_file or not secret_file:
                raise ValueError(
                    "KIWOOM_REST_APP_KEY_FILE and KIWOOM_REST_APP_SECRET_FILE "
                    "must be set together"
                )
            return cls(
                app_key=cls._read_secret_file(key_file, "Kiwoom REST App Key"),
                app_secret=cls._read_secret_file(
                    secret_file,
                    "Kiwoom REST App Secret",
                ),
                source="local_text_files",
            )

        raise ValueError(
            "Configure Kiwoom REST credentials using direct values or local text-file paths"
        )


@dataclass(frozen=True)
class KiwoomHttpResponse:
    status: int
    headers: Mapping[str, str]
    payload: object


class KiwoomHttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> KiwoomHttpResponse: ...


class KiwoomUrllibTransport:
    """Small JSON transport that never logs request bodies or authorization data."""

    @staticmethod
    def _headers(values: Message | HTTPMessage) -> dict[str, str]:
        return {str(key): str(value) for key, value in values.items()}

    @staticmethod
    def _decode(raw: bytes) -> object:
        if not raw:
            return {}
        try:
            return cast(object, json.loads(raw.decode("utf-8-sig")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Kiwoom REST returned a non-JSON response") from exc

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> KiwoomHttpResponse:
        request = Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                return KiwoomHttpResponse(
                    status=int(response.status),
                    headers=self._headers(response.headers),
                    payload=self._decode(response.read()),
                )
        except HTTPError as exc:
            return KiwoomHttpResponse(
                status=int(exc.code),
                headers=self._headers(exc.headers),
                payload=self._decode(exc.read()),
            )
        except URLError as exc:
            raise OSError("Kiwoom REST network request failed") from exc


@dataclass(frozen=True)
class KiwoomAccessToken:
    token: str
    token_type: str
    expires_at: datetime


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Kiwoom REST token response must be a JSON object")
    return cast(Mapping[str, object], value)


def _safe_error(payload: object, status: int) -> str:
    if isinstance(payload, dict):
        code = str(
            payload.get("return_code", payload.get("code", "unknown"))
        ).strip()
        message = str(
            payload.get("return_msg", payload.get("message", "request failed"))
        ).strip()
        return f"Kiwoom REST HTTP {status}: code={code} message={message}"
    return f"Kiwoom REST HTTP {status}: request failed"


class KiwoomRestAuthClient:
    """OAuth readiness client with no account, market, or order methods."""

    def __init__(
        self,
        credentials: KiwoomRestCredentials,
        *,
        mock: bool = False,
        transport: KiwoomHttpTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.credentials = credentials
        self.base_url = MOCK_BASE_URL if mock else LIVE_BASE_URL
        if self.base_url not in _ALLOWED_BASE_URLS:
            raise ValueError("Only official Kiwoom REST hosts are allowed")
        self.transport = transport or KiwoomUrllibTransport()
        self.timeout_seconds = timeout_seconds

    @property
    def mode(self) -> str:
        return "mock" if self.base_url == MOCK_BASE_URL else "live"

    def authenticate(self) -> KiwoomAccessToken:
        request_payload = {
            "grant_type": "client_credentials",
            "appkey": self.credentials.app_key,
            "secretkey": self.credentials.app_secret,
        }
        response = self.transport.request(
            "POST",
            f"{self.base_url}{TOKEN_PATH}",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "Alpha-Cycle-Lab/0.1",
            },
            body=json.dumps(request_payload).encode("utf-8"),
            timeout_seconds=self.timeout_seconds,
        )
        if response.status != 200:
            raise ValueError(_safe_error(response.payload, response.status))
        payload = _mapping(response.payload)
        return_code = str(payload.get("return_code", "")).strip()
        if return_code not in {"0", "0.0"}:
            raise ValueError(_safe_error(payload, response.status))
        token = str(payload.get("token", "")).strip()
        token_type = str(payload.get("token_type", "")).strip()
        expires_text = str(payload.get("expires_dt", "")).strip()
        if not token or not token_type or not expires_text:
            raise ValueError("Kiwoom REST token response is missing required fields")
        try:
            expires_at = datetime.strptime(expires_text, "%Y%m%d%H%M%S")
        except ValueError as exc:
            raise ValueError("Kiwoom REST token expiry has an invalid format") from exc
        return KiwoomAccessToken(
            token=token,
            token_type=token_type,
            expires_at=expires_at,
        )


__all__ = [
    "KiwoomAccessToken",
    "KiwoomHttpResponse",
    "KiwoomRestAuthClient",
    "KiwoomRestCredentials",
    "LIVE_BASE_URL",
    "MOCK_BASE_URL",
    "TOKEN_PATH",
]
