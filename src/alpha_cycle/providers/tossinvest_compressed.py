"""Compression-aware TossInvest transport used by the public provider export."""

from __future__ import annotations

import gzip
import json
import time
import zlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.message import Message
from http.client import HTTPMessage
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from alpha_cycle.providers.tossinvest import HttpResponse, HttpTransport, TossInvestCredentials
from alpha_cycle.providers.tossinvest import (
    TossInvestReadOnlyClient as _BaseTossInvestReadOnlyClient,
)


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _first_text(mapping: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _request_stage(url: str) -> str:
    return "auth" if "/oauth2/token" in url else "market-data"


def _normalize_error_payload(
    payload: object,
    *,
    status: int,
    headers: Mapping[str, str],
    url: str,
) -> object:
    """Normalize provider and edge-generated JSON errors into the documented envelope."""
    if status < 400 or not isinstance(payload, dict):
        return payload

    request_id = (
        _first_text(payload, ("requestId", "request_id"))
        or _header_value(headers, "X-Request-Id")
        or _header_value(headers, "x-amz-cf-id")
        or ""
    )
    nested = payload.get("error")
    if isinstance(nested, dict):
        normalized = dict(nested)
        if request_id and not str(normalized.get("requestId", "")).strip():
            normalized["requestId"] = request_id
        return {"error": normalized}

    stage = _request_stage(url)
    code = _first_text(
        payload,
        ("code", "errorCode", "error_code", "type", "title"),
    ) or f"{stage}-http-{status}"
    message = _first_text(
        payload,
        ("message", "error_description", "detail", "description"),
    )
    if message is None and isinstance(nested, str) and nested.strip():
        message = nested.strip()
    if message is None:
        keys = ",".join(sorted(str(key) for key in payload)[:12])
        message = f"{stage} request was rejected; response_keys={keys or 'none'}"
    else:
        message = f"{stage} request rejected: {message}"

    error: dict[str, object] = {"code": code, "message": message}
    if request_id:
        error["requestId"] = request_id
    return {"error": error}


class DecompressingUrllibTransport:
    """Decode gzip/deflate JSON responses before parsing them."""

    @staticmethod
    def _headers(values: Message | HTTPMessage) -> dict[str, str]:
        return {str(key): str(value) for key, value in values.items()}

    @staticmethod
    def _decompress(raw: bytes, headers: Mapping[str, str]) -> bytes:
        encoding = (_header_value(headers, "Content-Encoding") or "").strip().lower()
        try:
            if encoding in {"gzip", "x-gzip"} or raw.startswith(b"\x1f\x8b"):
                return gzip.decompress(raw)
            if encoding == "deflate":
                try:
                    return zlib.decompress(raw)
                except zlib.error:
                    return zlib.decompress(raw, -zlib.MAX_WBITS)
            if encoding in {"", "identity"}:
                return raw
        except (OSError, zlib.error) as exc:
            encoding_label = encoding or "unknown"
            raise ValueError(
                f"TossInvest response decompression failed: content_encoding={encoding_label}"
            ) from exc
        raise ValueError(f"Unsupported TossInvest content encoding: {encoding}")

    @classmethod
    def _decode(
        cls,
        raw: bytes,
        *,
        status: int,
        headers: Mapping[str, str],
    ) -> object:
        if not raw:
            return {}
        decoded_raw = cls._decompress(raw, headers)
        try:
            return cast(object, json.loads(decoded_raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            decoded = decoded_raw.decode("utf-8", errors="replace")
            preview = " ".join(decoded.split())[:240]
            content_type = _header_value(headers, "Content-Type") or "unknown"
            content_encoding = _header_value(headers, "Content-Encoding") or "identity"
            request_id = (
                _header_value(headers, "X-Request-Id")
                or _header_value(headers, "x-amz-cf-id")
                or "unavailable"
            )
            raise ValueError(
                "TossInvest returned non-JSON content after decompression: "
                f"status={status}, content_type={content_type}, "
                f"content_encoding={content_encoding}, request_id={request_id}, "
                f"body_preview={preview!r}"
            ) from exc

    @classmethod
    def _response(
        cls,
        *,
        status: int,
        headers: Mapping[str, str],
        raw: bytes,
        url: str,
    ) -> HttpResponse:
        payload = cls._decode(raw, status=status, headers=headers)
        return HttpResponse(
            status=status,
            headers=headers,
            payload=_normalize_error_payload(
                payload,
                status=status,
                headers=headers,
                url=url,
            ),
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        request_headers = dict(headers)
        request_headers.setdefault("Accept-Encoding", "gzip, deflate")
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                response_headers = self._headers(response.headers)
                return self._response(
                    status=int(response.status),
                    headers=response_headers,
                    raw=response.read(),
                    url=url,
                )
        except HTTPError as exc:
            response_headers = self._headers(exc.headers)
            return self._response(
                status=int(exc.code),
                headers=response_headers,
                raw=exc.read(),
                url=url,
            )
        except (URLError, TimeoutError) as exc:
            raise OSError("TossInvest network request failed") from exc


class TossInvestReadOnlyClient(_BaseTossInvestReadOnlyClient):
    """Public client using the compression-aware transport by default."""

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
        super().__init__(
            credentials,
            transport=transport or DecompressingUrllibTransport(),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            sleep=sleep,
            now=now,
        )

    @classmethod
    def from_env(cls) -> TossInvestReadOnlyClient:
        return cls(TossInvestCredentials.from_env())
