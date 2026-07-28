"""Regression tests for compressed TossInvest JSON responses."""

from __future__ import annotations

import gzip
import json
import zlib

import pytest

from alpha_cycle.providers import TossInvestCredentials, TossInvestReadOnlyClient
from alpha_cycle.providers.tossinvest_compressed import DecompressingUrllibTransport


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
