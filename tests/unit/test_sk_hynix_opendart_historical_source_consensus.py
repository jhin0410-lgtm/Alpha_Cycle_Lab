from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

import alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_source_consensus as consensus
import alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_capture as capture
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DiscoveredPeriodicProductRevenue,
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
)
from alpha_cycle.providers.opendart import CorpCode
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentArchive,
    DisclosureDocumentEvidence,
)


def _spec(*, year: int = 2016) -> PeriodicProductRevenueSpec:
    return PeriodicProductRevenueSpec(
        document_id=f"test-{year}q1",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="opendart",
        report_name_exact=f"분기보고서 ({year}.03)",
        discovery_begin_date=date(year, 4, 1),
        discovery_end_date=date(year, 5, 31),
        period_start=date(year, 1, 1),
        period_end=date(year, 3, 31),
        parser_id=HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
        expected_identity_anchors=("SK hynix", "3개월", "백만원"),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND",),
            "other_products_services": ("기타",),
            "reported_company_revenue": ("합계",),
        },
    )


def _metrics() -> ProductRevenueMetrics:
    return ProductRevenueMetrics(
        unit="KRW_million",
        dram_total=60.0,
        nand_and_solutions=20.0,
        other_products_services=4.0,
        reported_company_revenue=84.0,
        direct_sum=84.0,
        reconciliation_delta=0.0,
    )


def _witness_text(*, other: str = "4", unit: str = "백만원") -> str:
    return "\n".join(
        (
            "SK hynix",
            f"(단위: {unit})",
            "DRAM",
            "60",
            "50",
            "NAND",
            "20",
            "18",
            "기 타",
            other,
            "3",
            "합 계",
            "84",
            "71",
        )
    )


def _raise_text(*_args: object, **_kwargs: object) -> ProductRevenueMetrics:
    raise ValueError("normalized text lost historical table structure")


def _unexpected_archive(*_args: object, **_kwargs: object) -> ProductRevenueMetrics:
    raise AssertionError("archive fallback must not run for frozen certified periods")


def test_unanchored_historical_source_uses_archive_with_local_text_witness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = _metrics()
    monkeypatch.setattr(consensus, "parse_periodic_product_revenue_text", _raise_text)
    monkeypatch.setattr(
        consensus,
        "parse_periodic_product_revenue_archive",
        lambda _spec, _archive: metrics,
    )

    observed = consensus.parse_periodic_product_revenue_source_consensus(
        _spec(),
        _witness_text(),
        b"immutable-official-archive",
    )

    assert observed == metrics


def test_exact_q1_witness_does_not_require_printed_three_month_header() -> None:
    consensus.verify_historical_product_revenue_text_witness(
        _spec(),
        _witness_text(),
        _metrics(),
    )


def test_non_q1_historical_witness_still_requires_three_month_anchor() -> None:
    q2_spec = replace(
        _spec(),
        document_id="test-2016q2",
        report_name_exact="반기보고서 (2016.06)",
        discovery_begin_date=date(2016, 7, 1),
        discovery_end_date=date(2016, 8, 31),
        period_start=date(2016, 4, 1),
        period_end=date(2016, 6, 30),
    )
    with pytest.raises(ValueError, match="anchor missing: 3개월"):
        consensus.verify_historical_product_revenue_text_witness(
            q2_spec,
            _witness_text(),
            _metrics(),
        )


def test_unanchored_historical_source_rejects_text_witness_value_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = _metrics()
    monkeypatch.setattr(consensus, "parse_periodic_product_revenue_text", _raise_text)
    monkeypatch.setattr(
        consensus,
        "parse_periodic_product_revenue_archive",
        lambda _spec, _archive: metrics,
    )

    with pytest.raises(ValueError, match="normalized-text witness failed"):
        consensus.parse_periodic_product_revenue_source_consensus(
            _spec(),
            _witness_text(other="5"),
            b"immutable-official-archive",
        )


def test_unanchored_historical_source_requires_local_krw_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = _metrics()
    monkeypatch.setattr(consensus, "parse_periodic_product_revenue_text", _raise_text)
    monkeypatch.setattr(
        consensus,
        "parse_periodic_product_revenue_archive",
        lambda _spec, _archive: metrics,
    )

    text_without_unit = _witness_text().replace("(단위: 백만원)\n", "")
    with pytest.raises(ValueError, match="normalized-text witness failed"):
        consensus.parse_periodic_product_revenue_source_consensus(
            _spec(),
            text_without_unit,
            b"immutable-official-archive",
        )


def test_frozen_2021_period_does_not_fall_through_failed_text_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(consensus, "parse_periodic_product_revenue_text", _raise_text)
    monkeypatch.setattr(
        consensus,
        "parse_periodic_product_revenue_archive",
        _unexpected_archive,
    )

    with pytest.raises(ValueError, match="lost historical table structure"):
        consensus.parse_periodic_product_revenue_source_consensus(
            _spec(year=2021),
            _witness_text(),
            b"changed-archive-must-not-bypass-frozen-text-anchor",
        )


def test_capture_builder_uses_source_consensus(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _spec()
    receipt = "20160516001896"
    discovery = DiscoveredPeriodicProductRevenue(
        spec=spec,
        corp=CorpCode(
            corp_code="00164779",
            corp_name="SK하이닉스",
            stock_code="000660",
            modify_date=date(2016, 5, 16),
        ),
        rcept_no=receipt,
        report_name=spec.report_name_exact,
        receipt_date=date(2016, 5, 16),
    )
    archive_bytes = b"immutable-official-archive"
    text = _witness_text()
    evidence = DisclosureDocumentEvidence(
        rcept_no=receipt,
        retrieved_at=datetime(2016, 5, 16, 12, tzinfo=UTC),
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        archive_bytes=len(archive_bytes),
        member_count=1,
        text_member_count=1,
        uncompressed_bytes=len(text.encode()),
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        text_chars=len(text),
        text_truncated=False,
        text=text,
        members=(),
        warnings=(),
    )
    archive = DisclosureDocumentArchive(evidence=evidence, archive_bytes=archive_bytes)
    metrics = _metrics()
    calls: list[tuple[PeriodicProductRevenueSpec, str, bytes]] = []

    def _source_consensus(
        actual_spec: PeriodicProductRevenueSpec,
        actual_text: str,
        actual_archive: bytes,
    ) -> ProductRevenueMetrics:
        calls.append((actual_spec, actual_text, actual_archive))
        return metrics

    monkeypatch.setattr(
        capture,
        "parse_periodic_product_revenue_source_consensus",
        _source_consensus,
    )

    certification = capture.build_periodic_product_revenue_certification(
        discovery,
        archive,
        evaluation_date=date(2016, 5, 16),
    )

    assert certification.metrics == metrics
    assert calls == [(spec, text, archive_bytes)]


def test_current_text_archive_consensus_contract_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_spec = replace(
        _spec(),
        document_id="test-current",
        parser_id="skhynix_opendart_half_year_product_revenue_2026q2_v1",
    )
    metrics = _metrics()
    monkeypatch.setattr(
        consensus,
        "parse_periodic_product_revenue_text",
        lambda _spec, _text: metrics,
    )
    monkeypatch.setattr(
        consensus,
        "parse_periodic_product_revenue_archive",
        lambda _spec, _archive: metrics,
    )

    assert (
        consensus.parse_periodic_product_revenue_source_consensus(
            current_spec,
            "current normalized text",
            b"current archive",
        )
        == metrics
    )
