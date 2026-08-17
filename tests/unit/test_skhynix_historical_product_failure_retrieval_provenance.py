from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    load_failure_diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_capture import (
    _write_failure_bundle,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DiscoveredPeriodicProductRevenue,
    PeriodicProductRevenueSpec,
)
from alpha_cycle.providers.opendart import CorpCode
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentArchive,
    DisclosureDocumentEvidence,
)


def _discovery() -> DiscoveredPeriodicProductRevenue:
    spec = PeriodicProductRevenueSpec(
        document_id="failure-provenance-test",
        ticker="000660",
        issuer_name="SK하이닉스",
        source_id="opendart",
        report_name_exact="분기보고서 (2024.03)",
        discovery_begin_date=date(2024, 5, 1),
        discovery_end_date=date(2024, 5, 31),
        period_start=date(2024, 1, 1),
        period_end=date(2024, 3, 31),
        parser_id="skhynix_opendart_periodic_product_revenue_v1",
        expected_identity_anchors=("DRAM", "NAND", "백만원"),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND", "NAND Flash"),
            "other_products_services": ("기타",),
            "reported_company_revenue": ("합계",),
        },
    )
    return DiscoveredPeriodicProductRevenue(
        spec=spec,
        corp=CorpCode(
            corp_code="00164779",
            corp_name="SK하이닉스",
            stock_code="000660",
            modify_date=date(2024, 1, 1),
        ),
        rcept_no="20240516001638",
        report_name=spec.report_name_exact,
        receipt_date=date(2024, 5, 16),
    )


def _archive() -> DisclosureDocumentArchive:
    archive_bytes = b"preserved-opendart-archive-bytes"
    text = "DRAM\nNAND Flash\n기타\n합계"
    text_bytes = text.encode("utf-8")
    evidence = DisclosureDocumentEvidence(
        rcept_no="20240516001638",
        retrieved_at=datetime(2024, 5, 16, 9, 30, tzinfo=UTC),
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        archive_bytes=len(archive_bytes),
        member_count=1,
        text_member_count=1,
        uncompressed_bytes=len(text_bytes),
        text_sha256=hashlib.sha256(text_bytes).hexdigest(),
        text_chars=len(text),
        text_truncated=False,
        text=text,
        members=(),
        warnings=(),
    )
    return DisclosureDocumentArchive(evidence=evidence, archive_bytes=archive_bytes)


def _bundle(tmp_path: Path) -> Path:
    return _write_failure_bundle(
        tmp_path,
        discovery=_discovery(),
        archive=_archive(),
        error=ValueError("parser failed for test"),
        captured_at=datetime(2024, 5, 16, 9, 31, tzinfo=UTC),
    )


def _payload(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return {str(key): value for key, value in raw.items()}


def _rewrite(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def test_failure_bundle_preserves_exact_retrieval_provenance(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    payload = _payload(path)

    assert payload["retrieved_at"] == "2024-05-16T09:30:00+00:00"
    assert payload["receipt_date"] == "2024-05-16"
    assert payload["text_truncated"] is False
    assert payload["archive_bytes"] == len(_archive().archive_bytes)
    assert payload["text_chars"] == len(_archive().evidence.text)

    diagnostic = load_failure_diagnostic("2024Q1", path)
    assert diagnostic.retrieved_at == datetime(2024, 5, 16, 9, 30, tzinfo=UTC)
    assert diagnostic.retrieval_provenance_complete is True
    assert diagnostic.source_certification_promoted is False


def test_legacy_failure_bundle_remains_valid_but_not_provenance_complete(
    tmp_path: Path,
) -> None:
    path = _bundle(tmp_path)
    payload = _payload(path)
    for key in (
        "retrieved_at",
        "text_truncated",
        "archive_bytes",
        "text_chars",
    ):
        payload.pop(key)
    _rewrite(path, payload)

    diagnostic = load_failure_diagnostic("2024Q1", path)
    assert diagnostic.receipt_date == date(2024, 5, 16)
    assert diagnostic.retrieved_at is None
    assert diagnostic.retrieval_provenance_complete is False


def test_failure_loader_rejects_naive_retrieval_timestamp(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    payload = _payload(path)
    payload["retrieved_at"] = "2024-05-16T09:30:00"
    _rewrite(path, payload)

    with pytest.raises(ValueError, match="retrieved_at must be timezone-aware"):
        load_failure_diagnostic("2024Q1", path)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("archive_bytes", 1, "archive byte count mismatch"),
        ("text_chars", 1, "normalized text char count mismatch"),
    ],
)
def test_failure_loader_rejects_preserved_size_mismatch(
    tmp_path: Path,
    field: str,
    replacement: int,
    message: str,
) -> None:
    path = _bundle(tmp_path)
    payload = _payload(path)
    payload[field] = replacement
    _rewrite(path, payload)

    with pytest.raises(ValueError, match=message):
        load_failure_diagnostic("2024Q1", path)


def test_failure_loader_rejects_retrieval_before_receipt(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    payload = _payload(path)
    payload["retrieved_at"] = "2024-05-15T23:59:59+00:00"
    _rewrite(path, payload)

    with pytest.raises(ValueError, match="retrieval precedes filing receipt"):
        load_failure_diagnostic("2024Q1", path)
