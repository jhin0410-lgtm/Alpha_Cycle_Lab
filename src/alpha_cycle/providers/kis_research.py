"""Read-only Korea Investment OpenAPI adapter for raw estimate-perform evidence.

This module intentionally exposes research/quotation data only. It contains no
account number, holdings, balance, order, or execution methods. The provider response
is kept semantically unclassified until its live field layout and provenance are
verified; the endpoint name alone does not establish multi-broker consensus or a
single-broker analyst estimate.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from alpha_cycle.providers.read_only_http import (
    HttpBytesResponse,
    UrllibReadOnlyTransport,
    decode_json,
)

KIS_REST_BASE_URL = "https://openapi.koreainvestment.com:9443"
KIS_TOKEN_ENDPOINT = "/oauth2/tokenP"
KIS_ESTIMATE_PERFORM_ENDPOINT = "/uapi/domestic-stock/v1/quotations/estimate-perform"
KIS_ESTIMATE_PERFORM_TR_ID = "HHKST668300C0"
KIS_RESEARCH_SOURCE_SCOPE = "kis_estimate_perform_raw_unclassified"
KOREA_TZ = ZoneInfo("Asia/Seoul")
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class KisResearchTransport(Protocol):
    """Injectable HTTP boundary used by the KIS estimate-perform adapter."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse: ...

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpBytesResponse: ...


class UrllibKisResearchTransport(UrllibReadOnlyTransport):
    """Standard-library GET transport plus OAuth-token POST support."""

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        request_headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": self.user_agent,
            **dict(headers),
        }
        request = Request(url, headers=request_headers, data=body, method="POST")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                response_headers = self._headers(response.headers)
                payload = self._decompress(response.read(), response_headers)
                return HttpBytesResponse(int(response.status), response_headers, payload)
        except HTTPError as exc:
            response_headers = self._headers(exc.headers)
            payload = self._decompress(exc.read(), response_headers)
            return HttpBytesResponse(int(exc.code), response_headers, payload)
        except (URLError, TimeoutError) as exc:
            raise OSError("KIS authentication network request failed") from exc


@dataclass(frozen=True)
class KisResearchCredentials:
    app_key: str
    app_secret: str

    def __post_init__(self) -> None:
        for name, value in (
            ("KIS_APP_KEY", self.app_key),
            ("KIS_APP_SECRET", self.app_secret),
        ):
            if not value.strip():
                raise ValueError(f"{name} cannot be blank")
            if "replace_with" in value.casefold():
                raise ValueError(f"{name} cannot use a placeholder value")
            if "\r" in value or "\n" in value:
                raise ValueError(f"{name} cannot contain a newline")

    @classmethod
    def from_env(cls) -> KisResearchCredentials:
        app_key = os.environ.get("KIS_APP_KEY", "")
        app_secret = os.environ.get("KIS_APP_SECRET", "")
        if not app_key.strip() or not app_secret.strip():
            raise ValueError(
                "KIS research credentials are not configured: "
                "KIS_APP_KEY and KIS_APP_SECRET are required"
            )
        return cls(app_key=app_key, app_secret=app_secret)


@dataclass(frozen=True)
class KisEstimatePerformEvidence:
    symbol: str
    retrieved_at: datetime
    endpoint: str
    tr_id: str
    source_scope: str
    raw_response_sha256: str
    raw_payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if len(self.symbol) != 6 or not self.symbol.isdigit():
            raise ValueError("KIS research symbol must be a six-digit stock code")
        if len(self.raw_response_sha256) != 64:
            raise ValueError("raw_response_sha256 must be a SHA-256 hex digest")
        if self.source_scope != KIS_RESEARCH_SOURCE_SCOPE:
            raise ValueError("Unexpected KIS research source scope")

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "retrieved_at": self.retrieved_at.isoformat(),
            "provider": "korea_investment_openapi",
            "endpoint": self.endpoint,
            "tr_id": self.tr_id,
            "source_scope": self.source_scope,
            "raw_response_sha256": self.raw_response_sha256,
            "raw_payload": dict(self.raw_payload),
        }


@dataclass(frozen=True)
class _AccessToken:
    value: str
    expires_at: datetime


class KisResearchReadOnlyClient:
    """Fetch KIS estimate-perform evidence without account or order access."""

    def __init__(
        self,
        credentials: KisResearchCredentials,
        *,
        transport: KisResearchTransport | None = None,
        base_url: str = KIS_REST_BASE_URL,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(KOREA_TZ),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if not base_url.startswith("https://"):
            raise ValueError("KIS base URL must use HTTPS")
        self.credentials = credentials
        self.transport = transport or UrllibKisResearchTransport()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep = sleep
        self.now = now
        self._access_token: _AccessToken | None = None

    @classmethod
    def from_env(cls, **kwargs: object) -> KisResearchReadOnlyClient:
        return cls(KisResearchCredentials.from_env(), **kwargs)  # type: ignore[arg-type]

    @staticmethod
    def _symbol(value: object) -> str:
        symbol = str(value).strip()
        if len(symbol) != 6 or not symbol.isdigit():
            raise ValueError("KIS research symbol must be a six-digit stock code")
        return symbol

    def _clock(self) -> datetime:
        value = self.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("KIS research client clock must be timezone-aware")
        return value

    def _token_expiry(self, payload: Mapping[str, object], now: datetime) -> datetime:
        raw = payload.get("access_token_token_expired")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
            else:
                return parsed.replace(tzinfo=KOREA_TZ)
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, int) and not isinstance(expires_in, bool) and expires_in > 0:
            return now + timedelta(seconds=expires_in)
        return now + timedelta(minutes=30)

    def _issue_access_token(self) -> _AccessToken:
        now = self._clock()
        request_payload = json.dumps(
            {
                "grant_type": "client_credentials",
                "appkey": self.credentials.app_key,
                "appsecret": self.credentials.app_secret,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        response = self.transport.post(
            self.base_url + KIS_TOKEN_ENDPOINT,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=request_payload,
            timeout_seconds=self.timeout_seconds,
        )
        if response.status != 200:
            raise ValueError(f"KIS OAuth token request failed: HTTP {response.status}")
        decoded = decode_json(response.body, provider="KIS OAuth")
        if not isinstance(decoded, dict):
            raise ValueError("KIS OAuth token response must be a JSON object")
        payload = cast(Mapping[str, object], decoded)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise ValueError("KIS OAuth token response has no access_token")
        return _AccessToken(
            value=token.strip(),
            expires_at=self._token_expiry(payload, now),
        )

    def _token(self) -> str:
        now = self._clock()
        token = self._access_token
        if token is None or token.expires_at <= now + timedelta(minutes=1):
            token = self._issue_access_token()
            self._access_token = token
        return token.value

    @staticmethod
    def _api_error(payload: Mapping[str, object]) -> str:
        code = str(payload.get("msg_cd", "unknown")).strip() or "unknown"
        message = str(payload.get("msg1", "request failed")).strip() or "request failed"
        return f"KIS research API failed: code={code} message={message}"

    def _research_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self._token()}",
            "appkey": self.credentials.app_key,
            "appsecret": self.credentials.app_secret,
            "tr_id": KIS_ESTIMATE_PERFORM_TR_ID,
            "tr_cont": "",
            "custtype": "P",
        }

    def estimate_perform(self, symbol: object) -> KisEstimatePerformEvidence:
        """Fetch the official KIS estimate-perform payload for one stock."""

        normalized = self._symbol(symbol)
        url = (
            self.base_url
            + KIS_ESTIMATE_PERFORM_ENDPOINT
            + "?"
            + urlencode({"SHT_CD": normalized})
        )
        response: HttpBytesResponse | None = None
        for attempt in range(self.max_retries + 1):
            response = self.transport.get(
                url,
                headers=self._research_headers(),
                timeout_seconds=self.timeout_seconds,
            )
            if response.status not in _RETRYABLE_STATUS or attempt >= self.max_retries:
                break
            self.sleep(min(float(2**attempt), 30.0))
        assert response is not None
        if response.status != 200:
            raise ValueError(f"KIS research request failed: HTTP {response.status}")
        decoded = decode_json(response.body, provider="KIS research")
        if not isinstance(decoded, dict):
            raise ValueError("KIS research response must be a JSON object")
        payload = cast(Mapping[str, object], decoded)
        if str(payload.get("rt_cd", "")).strip() != "0":
            raise ValueError(self._api_error(payload))
        for output_name in ("output1", "output2", "output3", "output4"):
            if output_name not in payload:
                raise ValueError(f"KIS research response is missing {output_name}")
        for output_name in ("output2", "output3", "output4"):
            if not isinstance(payload.get(output_name), list):
                raise ValueError(f"KIS research {output_name} must be an array")
        output1 = payload.get("output1")
        if not isinstance(output1, (dict, list)):
            raise ValueError("KIS research output1 must be an object or array")
        retrieved_at = self._clock()
        return KisEstimatePerformEvidence(
            symbol=normalized,
            retrieved_at=retrieved_at,
            endpoint=KIS_ESTIMATE_PERFORM_ENDPOINT,
            tr_id=KIS_ESTIMATE_PERFORM_TR_ID,
            source_scope=KIS_RESEARCH_SOURCE_SCOPE,
            raw_response_sha256=hashlib.sha256(response.body).hexdigest(),
            raw_payload=payload,
        )


__all__ = [
    "KIS_ESTIMATE_PERFORM_ENDPOINT",
    "KIS_ESTIMATE_PERFORM_TR_ID",
    "KIS_RESEARCH_SOURCE_SCOPE",
    "KisEstimatePerformEvidence",
    "KisResearchCredentials",
    "KisResearchReadOnlyClient",
]
