"""Small read-only HTTP boundary shared by official data-provider adapters."""

from __future__ import annotations

import gzip
import json
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.message import Message
from http.client import HTTPMessage
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HttpBytesResponse:
    """HTTP status, headers, and decompressed response bytes."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpBytesTransport(Protocol):
    """Injectable HTTP GET boundary for production and mock tests."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse: ...


def header_value(headers: Mapping[str, str], name: str) -> str | None:
    """Return one header value without relying on case-sensitive mappings."""

    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def decode_json(body: bytes, *, provider: str) -> object:
    """Decode a provider JSON body without exposing credentials or request URLs."""

    try:
        return cast(object, json.loads(body.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        preview = " ".join(body.decode("utf-8", errors="replace").split())[:160]
        raise ValueError(f"{provider} returned invalid JSON: body_preview={preview!r}") from exc


class UrllibReadOnlyTransport:
    """Standard-library GET transport with gzip and deflate support."""

    user_agent = "Alpha-Cycle-Lab/0.1"

    @staticmethod
    def _headers(values: Message | HTTPMessage) -> dict[str, str]:
        return {str(key): str(value) for key, value in values.items()}

    @staticmethod
    def _decompress(body: bytes, headers: Mapping[str, str]) -> bytes:
        encoding = (header_value(headers, "Content-Encoding") or "").strip().lower()
        try:
            if encoding in {"gzip", "x-gzip"} or body.startswith(b"\x1f\x8b"):
                return gzip.decompress(body)
            if encoding == "deflate":
                try:
                    return zlib.decompress(body)
                except zlib.error:
                    return zlib.decompress(body, -zlib.MAX_WBITS)
            if encoding in {"", "identity"}:
                return body
        except (OSError, zlib.error) as exc:
            raise ValueError("Provider response decompression failed") from exc
        raise ValueError(f"Unsupported provider content encoding: {encoding}")

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        request_headers = {
            "Accept": "application/json, application/zip, application/xml",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": self.user_agent,
            **dict(headers),
        }
        request = Request(url, headers=request_headers, method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                response_headers = self._headers(response.headers)
                body = self._decompress(response.read(), response_headers)
                return HttpBytesResponse(int(response.status), response_headers, body)
        except HTTPError as exc:
            response_headers = self._headers(exc.headers)
            body = self._decompress(exc.read(), response_headers)
            return HttpBytesResponse(int(exc.code), response_headers, body)
        except (URLError, TimeoutError) as exc:
            raise OSError("Provider network request failed") from exc


class RetryingReadOnlyClient:
    """Bounded retry helper for idempotent official-data GET requests."""

    retryable_status = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        transport: HttpBytesTransport | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        sleep: Callable[[float], None],
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.transport = transport or UrllibReadOnlyTransport()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep = sleep

    @staticmethod
    def _backoff(response: HttpBytesResponse, attempt: int) -> float:
        raw = header_value(response.headers, "Retry-After")
        if raw is not None:
            try:
                seconds = float(raw)
            except ValueError:
                seconds = 0.0
            if seconds > 0:
                return min(seconds, 60.0)
        return min(float(2**attempt), 30.0)

    def _get(self, url: str) -> HttpBytesResponse:
        for attempt in range(self.max_retries + 1):
            response = self.transport.get(
                url,
                headers={},
                timeout_seconds=self.timeout_seconds,
            )
            if response.status not in self.retryable_status or attempt >= self.max_retries:
                return response
            self.sleep(self._backoff(response, attempt))
        raise AssertionError("unreachable retry loop")
