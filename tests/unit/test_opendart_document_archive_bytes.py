from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, datetime

from alpha_cycle.providers.opendart_documents import OpenDartDisclosureDocumentClient

RECEIPT = "20260814001234"


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body


class _Client:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    def _url(self, path, params):
        assert path == "/api/document.xml"
        assert params == {"rcept_no": RECEIPT}
        return "https://opendart.fss.or.kr/api/document.xml"

    def _get(self, url):
        assert url == "https://opendart.fss.or.kr/api/document.xml"
        self.calls += 1
        return _Response(self.body)

    def now(self):
        return datetime(2026, 8, 14, 9, 0, tzinfo=UTC)


def _zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", "<html><body>반기보고서</body></html>")
    return buffer.getvalue()


def test_document_with_archive_fetches_once_and_preserves_exact_bytes() -> None:
    raw = _zip()
    client = _Client(raw)
    result = OpenDartDisclosureDocumentClient(client).document_with_archive(RECEIPT)  # type: ignore[arg-type]
    assert client.calls == 1
    assert result.archive_bytes == raw
    assert result.evidence.archive_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.evidence.archive_bytes == len(raw)


def test_legacy_document_api_remains_compatible() -> None:
    raw = _zip()
    client = _Client(raw)
    result = OpenDartDisclosureDocumentClient(client).document(RECEIPT)  # type: ignore[arg-type]
    assert client.calls == 1
    assert result.rcept_no == RECEIPT
    assert result.archive_sha256 == hashlib.sha256(raw).hexdigest()
