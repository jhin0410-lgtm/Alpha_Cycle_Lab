from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_capture import (
    _write_normalized_text,
)
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentArchive,
    DisclosureDocumentEvidence,
)


def _archive(text: str, *, text_sha256: str | None = None) -> DisclosureDocumentArchive:
    archive_bytes = b"synthetic-archive"
    encoded = text.encode("utf-8")
    evidence = DisclosureDocumentEvidence(
        rcept_no="20240516000001",
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        archive_bytes=len(archive_bytes),
        member_count=1,
        text_member_count=1,
        uncompressed_bytes=len(encoded),
        text_sha256=text_sha256 or hashlib.sha256(encoded).hexdigest(),
        text_chars=len(text),
        text_truncated=False,
        text=text,
        members=(),
        warnings=(),
    )
    return DisclosureDocumentArchive(evidence=evidence, archive_bytes=archive_bytes)


def test_normalized_text_is_persisted_as_exact_hashed_utf8_bytes(tmp_path) -> None:
    text = "첫째 줄\n둘째 줄\nthird line"
    archive = _archive(text)
    path = tmp_path / "normalized_document.txt"

    _write_normalized_text(path, archive)

    expected = text.encode("utf-8")
    assert path.read_bytes() == expected
    assert hashlib.sha256(path.read_bytes()).hexdigest() == archive.evidence.text_sha256
    assert b"\r\n" not in path.read_bytes()


def test_normalized_text_writer_rejects_in_memory_hash_mismatch(tmp_path) -> None:
    archive = _archive("line one\nline two", text_sha256="0" * 64)

    with pytest.raises(ValueError, match="in-memory hash mismatch"):
        _write_normalized_text(tmp_path / "normalized_document.txt", archive)
