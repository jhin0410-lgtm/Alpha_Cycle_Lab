"""Regression tests for compressed TossInvest JSON responses."""

from __future__ import annotations

import gzip
import json
import zlib

import pytest

from alpha_cycle.providers import TossInvestCredentials, TossInvestReadOnlyClient
from alpha_cycle.providers.tossinvest_compressed import (
    DecompressingUrllibTransport,
    _normalize_error_payload,
)


def _encoded(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_gzip_json_is_decompressed_before_parsing() -> None:
    payload = {"error": {"code": "forbidden", "message": "access denied"}}
    decoded = DecompressingUrllibTransport._decode(
        gzip.compress(_encoded(payload)),
        status=403,
        headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
    )
    assert decoded == payload


def test_gzip_magic_bytes_are_detected_without_header() -> None:
    payload = {"result": [{"symbol": "005930"}]}
    decoded = DecompressingUrllibTransport._decode(
        gzip.compress(_encoded(payload)),
        status=200,
        headers={"Content-Type": "application/json"},
    )
    assert decoded == payload


def test_deflate_json_is_decompressed_before_parsing() -> None:
    payload = {"result": {"candles": []}}
    decoded = DecompressingUrllibTransport._decode(
        zlib.compress(_encoded(payload)),
        status=200,
        headers={"Content-Encoding": "deflate"},
    )
    assert decoded == payload


def test_unsupported_content_encoding_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported TossInvest content encoding"):
        DecompressingUrllibTransport._decode(
            _encoded({"result": []}),
            status=200,
            headers={"Content-Encoding": "br"},
        )


def test_public_client_uses_compression_aware_transport() -> None:
    client = TossInvestReadOnlyClient(TossInvestCredentials("client", "secret"))
    assert isinstance(client.transport, DecompressingUrllibTransport)


def test_documented_error_envelope_preserves_code_and_adds_header_request_id() -> None:
    normalized = _normalize_error_payload(
        {"error": {"code": "forbidden", "message": "권한이 부족합니다."}},
        status=403,
        headers={"X-Request-Id": "request-123"},
        url="https://openapi.tossinvest.com/api/v1/prices?symbols=005930",
    )
    assert normalized == {
        "error": {
            "code": "forbidden",
            "message": "권한이 부족합니다.",
            "requestId": "request-123",
        }
    }


def test_top_level_edge_error_is_normalized_with_auth_stage() -> None:
    normalized = _normalize_error_payload(
        {"message": "Forbidden"},
        status=403,
        headers={"x-amz-cf-id": "edge-request-456"},
        url="https://openapi.tossinvest.com/oauth2/token",
    )
    assert normalized == {
        "error": {
            "code": "auth-http-403",
            "message": "auth request rejected: Forbidden",
            "requestId": "edge-request-456",
        }
    }


def test_unknown_edge_error_reports_safe_keys_and_market_data_stage() -> None:
    normalized = _normalize_error_payload(
        {"reason": "policy"},
        status=403,
        headers={},
        url="https://openapi.tossinvest.com/api/v1/prices?symbols=005930",
    )
    assert normalized == {
        "error": {
            "code": "market-data-http-403",
            "message": "market-data request was rejected; response_keys=reason",
        }
    }
