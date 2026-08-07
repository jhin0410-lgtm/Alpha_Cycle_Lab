"""Tests for immutable OpenDART original-document evidence collection."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.data.research import RevisionPolicy
from alpha_cycle.intelligence import fundamental_macro_documents as documents
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroCollector as BaseFundamentalMacroCollector,
)
from alpha_cycle.intelligence.fundamental_macro import FundamentalMacroSnapshot
from alpha_cycle.providers.opendart import OpenDartCredentials, OpenDartReadOnlyClient
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentEvidence,
    DisclosureDocumentMemberEvidence,
    OpenDartDisclosureDocumentClient,
)
from alpha_cycle.providers.read_only_http import HttpBytesResponse

NOW = datetime(2026, 8, 7, 7, 30, tzinfo=UTC)


class FakeTransport:
    def __init__(self, responses: list[HttpBytesResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        assert timeout_seconds > 0
        assert isinstance(headers, Mapping)
        self.urls.append(url)
        if not self.responses:
            raise AssertionError("No fake response remains")
        return self.responses.pop(0)


def _document_zip(*, unsafe: bool = False) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        name = "../escape.xml" if unsafe else "document.xml"
        archive.writestr(
            name,
            "<?xml version='1.0' encoding='utf-8'?><DOC><P>신규 시설투자 1조원</P></DOC>",
        )
        if not unsafe:
            archive.writestr("detail.html", "<html><body>투자기간 2026년</body></html>")
            archive.writestr("image.png", b"\x89PNG\r\n")
    return stream.getvalue()


def test_original_document_zip_is_hashed_and_text_normalized() -> None:
    body = _document_zip()
    transport = FakeTransport([HttpBytesResponse(200, {}, body)])
    client = OpenDartReadOnlyClient(
        OpenDartCredentials("secret"),
        transport=transport,
        now=lambda: NOW,
    )

    evidence = OpenDartDisclosureDocumentClient(client).document("20260807000001")

    assert evidence.rcept_no == "20260807000001"
    assert evidence.archive_sha256 == hashlib.sha256(body).hexdigest()
    assert evidence.member_count == 3
    assert evidence.text_member_count == 2
    assert "신규 시설투자 1조원" in evidence.text
    assert "투자기간 2026년" in evidence.text
    assert evidence.text_sha256 == hashlib.sha256(evidence.text.encode("utf-8")).hexdigest()
    assert evidence.retrieved_at == NOW
    assert evidence.text_truncated is False
    assert "non_text_member_skipped:image.png" in evidence.warnings
    assert "/api/document.xml?" in transport.urls[0]
    assert "rcept_no=20260807000001" in transport.urls[0]


def test_original_document_rejects_archive_path_traversal() -> None:
    transport = FakeTransport([HttpBytesResponse(200, {}, _document_zip(unsafe=True))])
    client = OpenDartReadOnlyClient(OpenDartCredentials("secret"), transport=transport)

    with pytest.raises(ValueError, match="unsafe member path"):
        OpenDartDisclosureDocumentClient(client).document("20260807000001")


def test_original_document_api_error_is_sanitized() -> None:
    body = (
        b"<result><status>014</status><message>file not found</message></result>"
    )
    transport = FakeTransport([HttpBytesResponse(200, {}, body)])
    client = OpenDartReadOnlyClient(OpenDartCredentials("secret"), transport=transport)

    with pytest.raises(ValueError) as exc_info:
        OpenDartDisclosureDocumentClient(client).document("20260807000001")
    assert "status=014" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


def _disclosures() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "rcept_no": "20260624000420",
                "report_name": "주요사항보고서(유상증자결정)",
                "receipt_date": date(2026, 6, 24),
                "is_correction": False,
            },
            {
                "ticker": "000660",
                "rcept_no": "20260706000403",
                "report_name": "[기재정정]주요사항보고서(유상증자결정)",
                "receipt_date": date(2026, 7, 6),
                "is_correction": True,
            },
            {
                "ticker": "000660",
                "rcept_no": "20260710000404",
                "report_name": "[기재정정]주요사항보고서(유상증자결정)",
                "receipt_date": date(2026, 7, 10),
                "is_correction": True,
            },
            {
                "ticker": "000660",
                "rcept_no": "20260807000001",
                "report_name": "신규시설투자등",
                "receipt_date": date(2026, 8, 7),
                "is_correction": False,
            },
            {
                "ticker": "000660",
                "rcept_no": "20260317000001",
                "report_name": "사업보고서 (2025.12)",
                "receipt_date": date(2026, 3, 17),
                "is_correction": False,
            },
        ]
    )


def test_document_selection_keeps_latest_correction_and_excludes_periodic_reports() -> None:
    selected, warnings = documents.select_material_disclosure_documents(
        _disclosures(),
        evaluation_date=date(2026, 8, 7),
        max_documents_per_ticker=2,
    )

    receipts = set(selected["rcept_no"].astype(str))
    assert receipts == {"20260710000404", "20260807000001"}
    assert "20260624000420" not in receipts
    assert "20260706000403" not in receipts
    assert "20260317000001" not in receipts
    assert warnings == ()


def test_document_selection_records_capacity_without_calling_it_unavailable() -> None:
    selected, ledger, warnings = documents._selection_plan(
        _disclosures(),
        evaluation_date=date(2026, 8, 7),
        max_documents_per_ticker=1,
    )

    assert list(selected["rcept_no"].astype(str)) == ["20260807000001"]
    assert ledger["20260807000001"]["status"] == "selected_pending"
    assert ledger["20260710000404"]["status"] == "excluded_capacity"
    assert ledger["20260317000001"]["status"] == "excluded_periodic"
    assert warnings == ("disclosure_document_selection_truncated:000660:1/2",)


class FakeDocumentClient:
    def document(self, rcept_no: object) -> DisclosureDocumentEvidence:
        receipt = str(rcept_no)
        if receipt == "20260710000404":
            raise ValueError("document unavailable")
        text = "신규 시설투자 본문 증거"
        return DisclosureDocumentEvidence(
            rcept_no=receipt,
            retrieved_at=NOW + timedelta(minutes=1),
            archive_sha256="a" * 64,
            archive_bytes=100,
            member_count=1,
            text_member_count=1,
            uncompressed_bytes=200,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            text_chars=len(text),
            text_truncated=False,
            text=text,
            members=(
                DisclosureDocumentMemberEvidence(
                    name="document.xml",
                    sha256="b" * 64,
                    compressed_bytes=100,
                    uncompressed_bytes=200,
                    encoding="utf-8",
                    text_chars=len(text),
                ),
            ),
            warnings=(),
        )


def test_extended_collector_embeds_document_evidence_without_failing_on_one_missing_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = FundamentalMacroSnapshot(
        captured_at=NOW,
        evaluation_date=date(2026, 8, 7),
        revision_policy=RevisionPolicy.LATEST_KNOWN,
        financials=pd.DataFrame(),
        disclosures=_disclosures(),
        macro=pd.DataFrame(),
        raw_opendart={"000660": {"corp": {"stock_code": "000660"}}},
        raw_ecos={},
    )
    monkeypatch.setattr(
        BaseFundamentalMacroCollector,
        "collect",
        lambda self, *args, **kwargs: base,
    )

    collector = documents.FundamentalMacroCollector(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        document_client=FakeDocumentClient(),  # type: ignore[arg-type]
        max_documents_per_ticker=2,
    )
    snapshot = collector.collect(
        ["000660"],
        business_year=2025,
        report_code="11011",
        fs_div="CFS",
        disclosure_begin=date(2025, 8, 7),
        disclosure_end=date(2026, 8, 7),
        ecos_specs=(),
        evaluation_date=date(2026, 8, 7),
        revision_policy=RevisionPolicy.LATEST_KNOWN,
        market_snapshot=None,
    )

    raw = snapshot.raw_opendart
    assert isinstance(raw, dict)
    bundle = raw["_disclosure_document_evidence"]
    assert isinstance(bundle, dict)
    assert bundle["schema_version"] == 2
    stored = bundle["documents"]
    assert isinstance(stored, dict)
    assert stored["20260807000001"]["status"] == "collected"
    assert stored["20260710000404"]["status"] == "unavailable"
    assert stored["20260317000001"]["status"] == "excluded_periodic"
    assert bundle["status_counts"] == {
        "collected": 1,
        "unavailable": 1,
        "excluded_periodic": 1,
    }
    assert snapshot.captured_at == NOW + timedelta(minutes=1)
    assert any(
        warning == "disclosure_document_unavailable:000660:20260710000404"
        for warning in snapshot.warnings
    )
    assert json.dumps(raw, ensure_ascii=False)
    assert tmp_path.exists()
