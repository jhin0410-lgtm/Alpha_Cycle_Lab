"""Read-only Toss Securities Open API market-data client.

The adapter intentionally exposes no account or order mutation methods. It supports
OAuth2 client-credentials authentication plus the public market-data endpoints used
by the market-intelligence pipeline.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.message import Message
from http.client import HTTPMessage
from pathlib import Path
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OFFICIAL_BASE_URL = "https://openapi.tossinvest.com"
CLIENT_USER_AGENT = "Alpha-Cycle-Lab/0.1"
MAX_PRICE_SYMBOLS = 200
MAX_CANDLE_COUNT = 200
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
READ_ONLY_PATHS = frozenset(
    {
        "/api/v1/prices",
        "/api/v1/candles",
        "/api/v1/orderbook",
        "/api/v1/trades",
        "/api/v1/price-limits",
        "/api/v1/stocks",
        "/api/v1/exchange-rate",
        "/api/v1/market-calendar/KR",
        "/api/v1/market-calendar/US",
        "/api/v1/rankings",
        "/api/v1/market-indicators/prices",
    }
)


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _request_headers(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    result = {
        "Accept": "application/json",
        "User-Agent": CLIENT_USER_AGENT,
    }
    if extra is not None:
        result.update(extra)
    return result


@dataclass(frozen=True)
class TossInvestCredentials:
    """Local credentials loaded only from environment variables."""

    client_id: str
    client_secret: str
    base_url: str = OFFICIAL_BASE_URL

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> TossInvestCredentials:
        values = os.environ if environ is None else environ
        client_id = values.get("TOSSINVEST_CLIENT_ID", "").strip()
        client_secret = values.get("TOSSINVEST_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise ValueError(
                "TOSSINVEST_CLIENT_ID and TOSSINVEST_CLIENT_SECRET must be set locally"
            )
        if "replace_with" in client_id.lower() or "replace_with" in client_secret.lower():
            raise ValueError("TossInvest placeholder credentials cannot be used")
        return cls(client_id=client_id, client_secret=client_secret)

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != OFFICIAL_BASE_URL:
            raise ValueError("Only the official TossInvest API host is allowed")


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    payload: object


class HttpTransport(Protocol):
    """Small injectable HTTP boundary used by runtime code and mock tests."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse: ...


class UrllibTransport:
    """Standard-library JSON transport with safe diagnostics for edge/WAF responses."""

    @staticmethod
    def _headers(values: Message | HTTPMessage) -> dict[str, str]:
        return {str(key): str(value) for key, value in values.items()}

    @staticmethod
    def _decode(
        raw: bytes,
        *,
        status: int,
        headers: Mapping[str, str],
    ) -> object:
        if not raw:
            return {}
        try:
            text = raw.decode("utf-8")
            return cast(object, json.loads(text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            decoded = raw.decode("utf-8", errors="replace")
            preview = " ".join(decoded.split())[:240]
            content_type = _header_value(headers, "Content-Type") or "unknown"
            request_id = (
                _header_value(headers, "X-Request-Id")
                or _header_value(headers, "x-amz-cf-id")
                or "unavailable"
            )
            raise ValueError(
                "TossInvest returned non-JSON content: "
                f"status={status}, content_type={content_type}, "
                f"request_id={request_id}, body_preview={preview!r}"
            ) from exc

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        request = Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                response_headers = self._headers(response.headers)
                status = int(response.status)
                raw = response.read()
                return HttpResponse(
                    status=status,
                    headers=response_headers,
                    payload=self._decode(raw, status=status, headers=response_headers),
                )
        except HTTPError as exc:
            response_headers = self._headers(exc.headers)
            status = int(exc.code)
            raw = exc.read()
            return HttpResponse(
                status=status,
                headers=response_headers,
                payload=self._decode(raw, status=status, headers=response_headers),
            )
        except (URLError, TimeoutError) as exc:
            raise OSError("TossInvest network request failed") from exc


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_at: datetime

    def is_valid(self, now: datetime, *, safety_margin_seconds: int = 30) -> bool:
        return now + timedelta(seconds=safety_margin_seconds) < self.expires_at


@dataclass(frozen=True)
class MarketPrice:
    symbol: str
    timestamp: datetime
    last_price: Decimal
    currency: str


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    currency: str
    interval: str
    adjusted: bool


@dataclass(frozen=True)
class PriceBatch:
    prices: tuple[MarketPrice, ...]
    raw_payload: object
    response_headers: Mapping[str, str]


@dataclass(frozen=True)
class CandleBatch:
    symbol: str
    candles: tuple[Candle, ...]
    next_before: str | None
    raw_payload: object
    response_headers: Mapping[str, str]


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return cast(list[object], value)


def _text(value: object, field_name: str) -> str:
    result = str(value).strip()
    if not result or result.lower() in {"none", "nan"}:
        raise ValueError(f"{field_name} must be a non-empty string")
    return result


def _decimal(value: object, field_name: str, *, minimum: Decimal = Decimal("0")) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite() or result < minimum:
        raise ValueError(f"{field_name} must be finite and at least {minimum}")
    return result


def _aware_datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return parsed


def _error_detail(payload: object, status: int) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = str(error.get("code", "unknown-error"))
            message = str(error.get("message", "request failed"))
            request_id = str(error.get("requestId", "")).strip()
            suffix = f" request_id={request_id}" if request_id else ""
            return f"TossInvest HTTP {status}: {code}: {message}{suffix}"
    return f"TossInvest HTTP {status}: request failed"


class TossInvestReadOnlyClient:
    """OAuth2 market-data client whose route allow-list excludes all order APIs."""

    def __init__(
        self,
        credentials: TossInvestCredentials,
        *,
        transport: HttpTransport | None = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.credentials = credentials
        self.transport = transport or UrllibTransport()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep = sleep
        self.now = now
        self._token: AccessToken | None = None

    @classmethod
    def from_env(cls) -> TossInvestReadOnlyClient:
        return cls(TossInvestCredentials.from_env())

    def _backoff_seconds(self, response: HttpResponse, attempt: int) -> float:
        retry_after = _header_value(response.headers, "Retry-After")
        if retry_after is not None:
            try:
                parsed = float(retry_after)
            except ValueError:
                parsed = 0.0
            if parsed > 0:
                return min(parsed, 60.0)
        return min(float(2**attempt), 30.0)

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> HttpResponse:
        for attempt in range(self.max_retries + 1):
            response = self.transport.request(
                method,
                url,
                headers=headers,
                body=body,
                timeout_seconds=self.timeout_seconds,
            )
            if response.status not in RETRYABLE_STATUS or attempt >= self.max_retries:
                return response
            self.sleep(self._backoff_seconds(response, attempt))
        raise AssertionError("unreachable retry loop")

    @staticmethod
    def _token_fields(payload: object) -> tuple[str, int]:
        container = _mapping(payload, "token response")
        nested = container.get("result")
        if isinstance(nested, dict):
            container = cast(Mapping[str, object], nested)
        token = container.get("access_token", container.get("accessToken"))
        expires = container.get("expires_in", container.get("expiresIn"))
        token_text = _text(token, "access token")
        try:
            expires_seconds = int(str(expires))
        except (TypeError, ValueError) as exc:
            raise ValueError("token expiry must be an integer number of seconds") from exc
        if expires_seconds <= 0:
            raise ValueError("token expiry must be positive")
        return token_text, expires_seconds

    def authenticate(self, *, force: bool = False) -> AccessToken:
        now = self.now()
        if not force and self._token is not None and self._token.is_valid(now):
            return self._token
        body = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
            }
        ).encode("utf-8")
        response = self._request_with_retry(
            "POST",
            f"{self.credentials.base_url}/oauth2/token",
            headers=_request_headers(
                {"Content-Type": "application/x-www-form-urlencoded"}
            ),
            body=body,
        )
        if response.status != 200:
            raise ValueError(_error_detail(response.payload, response.status))
        value, expires_seconds = self._token_fields(response.payload)
        self._token = AccessToken(value=value, expires_at=now + timedelta(seconds=expires_seconds))
        return self._token

    def _authorized_get(self, path: str, query: Mapping[str, str]) -> HttpResponse:
        if path not in READ_ONLY_PATHS:
            raise ValueError(f"TossInvest path is not on the read-only allow-list: {path}")
        if "order" in path.lower():
            raise ValueError("Order endpoints are structurally disabled")
        url = f"{self.credentials.base_url}{path}?{urlencode(query)}"
        token = self.authenticate()
        response = self._request_with_retry(
            "GET",
            url,
            headers=_request_headers({"Authorization": f"Bearer {token.value}"}),
        )
        if response.status == 401:
            token = self.authenticate(force=True)
            response = self._request_with_retry(
                "GET",
                url,
                headers=_request_headers({"Authorization": f"Bearer {token.value}"}),
            )
        if response.status != 200:
            raise ValueError(_error_detail(response.payload, response.status))
        return response

    def prices(self, symbols: list[str] | tuple[str, ...]) -> PriceBatch:
        normalized = tuple(
            dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
        )
        if not normalized:
            raise ValueError("At least one symbol is required")
        if len(normalized) > MAX_PRICE_SYMBOLS:
            raise ValueError(f"TossInvest prices supports at most {MAX_PRICE_SYMBOLS} symbols")
        response = self._authorized_get("/api/v1/prices", {"symbols": ",".join(normalized)})
        payload = _mapping(response.payload, "price response")
        rows = _sequence(payload.get("result"), "price result")
        parsed: list[MarketPrice] = []
        for raw in rows:
            row = _mapping(raw, "price row")
            parsed.append(
                MarketPrice(
                    symbol=_text(row.get("symbol"), "price symbol").upper(),
                    timestamp=_aware_datetime(row.get("timestamp"), "price timestamp"),
                    last_price=_decimal(row.get("lastPrice"), "last price"),
                    currency=_text(row.get("currency"), "price currency").upper(),
                )
            )
        if {item.symbol for item in parsed} != set(normalized):
            raise ValueError("TossInvest price response did not match the requested symbol set")
        parsed.sort(key=lambda item: item.symbol)
        return PriceBatch(tuple(parsed), response.payload, dict(response.headers))

    def candles(
        self,
        symbol: str,
        *,
        interval: str,
        count: int = 100,
        before: datetime | None = None,
        adjusted: bool = False,
    ) -> CandleBatch:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        if interval not in {"1m", "1d"}:
            raise ValueError("interval must be 1m or 1d")
        if count <= 0 or count > MAX_CANDLE_COUNT:
            raise ValueError(f"count must be between 1 and {MAX_CANDLE_COUNT}")
        query = {
            "symbol": normalized,
            "interval": interval,
            "count": str(count),
            "adjusted": "true" if adjusted else "false",
        }
        if before is not None:
            if before.tzinfo is None or before.utcoffset() is None:
                raise ValueError("before must be timezone-aware")
            query["before"] = before.isoformat()
        response = self._authorized_get("/api/v1/candles", query)
        payload = _mapping(response.payload, "candle response")
        result = _mapping(payload.get("result"), "candle result")
        rows = _sequence(result.get("candles"), "candles")
        parsed: list[Candle] = []
        for raw in rows:
            row = _mapping(raw, "candle row")
            open_price = _decimal(row.get("openPrice"), "open price")
            high_price = _decimal(row.get("highPrice"), "high price")
            low_price = _decimal(row.get("lowPrice"), "low price")
            close_price = _decimal(row.get("closePrice"), "close price")
            if high_price < max(open_price, close_price, low_price):
                raise ValueError("candle high price is inconsistent")
            if low_price > min(open_price, close_price, high_price):
                raise ValueError("candle low price is inconsistent")
            parsed.append(
                Candle(
                    symbol=normalized,
                    timestamp=_aware_datetime(row.get("timestamp"), "candle timestamp"),
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=_decimal(row.get("volume"), "candle volume"),
                    currency=_text(row.get("currency"), "candle currency").upper(),
                    interval=interval,
                    adjusted=adjusted,
                )
            )
        parsed.sort(key=lambda item: item.timestamp)
        timestamps = [item.timestamp for item in parsed]
        if len(timestamps) != len(set(timestamps)):
            raise ValueError("TossInvest candle response contains duplicate timestamps")
        next_before_raw = result.get("nextBefore")
        next_before = None if next_before_raw in {None, ""} else str(next_before_raw)
        return CandleBatch(
            symbol=normalized,
            candles=tuple(parsed),
            next_before=next_before,
            raw_payload=response.payload,
            response_headers=dict(response.headers),
        )


def write_private_credentials_template(path: str | Path) -> Path:
    """Write a local-only template without real secrets for user setup."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "TOSSINVEST_CLIENT_ID=replace_with_local_secret\n"
        "TOSSINVEST_CLIENT_SECRET=replace_with_local_secret\n",
        encoding="utf-8",
    )
    return destination
