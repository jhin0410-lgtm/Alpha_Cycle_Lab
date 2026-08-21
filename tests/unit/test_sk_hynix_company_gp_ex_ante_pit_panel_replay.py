from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from alpha_cycle.intelligence import sk_hynix_company_gp_ex_ante_pit_panel_replay as replay
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_expansion import (
    PITPanelExpansionMapping,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
)


def _mapping() -> PITPanelExpansionMapping:
    return PITPanelExpansionMapping(
        source_period="2016Q1",
        target_period="2016Q2",
        report_code="11013",
        expected_receipt=None,
    )


def test_exact_name_recovery_is_used_only_after_registered_account_id_misses() -> None:
    rows = (
        {
            "sj_div": "CIS",
            "account_id": "legacy_revenue_id",
            "account_nm": "매출액",
            "bsns_year": "2016",
            "reprt_code": "11013",
            "rcept_no": "20160516000001",
            "thstrm_amount": "100000000",
        },
    )

    amount, receipt, basis = replay.select_company_account_for_replay(
        rows,
        ("ifrs-full_Revenue",),
        _mapping(),
        label="revenue",
    )

    assert amount == 100_000_000
    assert receipt == "20160516000001"
    assert basis == "exact_account_name"


def test_registered_account_id_keeps_precedence_over_name_fallback() -> None:
    rows = (
        {
            "sj_div": "CIS",
            "account_id": "ifrs-full_Revenue",
            "account_nm": "매출액",
            "bsns_year": "2016",
            "reprt_code": "11013",
            "rcept_no": "20160516000001",
            "thstrm_amount": "100000000",
        },
    )

    _amount, _receipt, basis = replay.select_company_account_for_replay(
        rows,
        ("ifrs-full_Revenue",),
        _mapping(),
        label="revenue",
    )

    assert basis == "registered_account_id"


def test_exact_name_recovery_never_accepts_fuzzy_account_name() -> None:
    rows = (
        {
            "sj_div": "CIS",
            "account_id": "legacy_revenue_id",
            "account_nm": "연결 매출액 합계",
            "bsns_year": "2016",
            "reprt_code": "11013",
            "rcept_no": "20160516000001",
            "thstrm_amount": "100000000",
        },
    )

    with pytest.raises(ValueError, match="exact-name account must resolve uniquely"):
        replay.select_company_account_for_replay(
            rows,
            ("ifrs-full_Revenue",),
            _mapping(),
            label="revenue",
        )


def test_immutable_receipt_replay_allows_later_retrieval_without_changing_availability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_date = date(2026, 8, 18)
    receipt_date = date(2021, 5, 17)
    receipt = "20210517000667"
    spec = PeriodicProductRevenueSpec(
        document_id="skhynix_000660_2021q1_ex_ante_pit_expansion",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="opendart",
        report_name_exact="분기보고서 (2021.03)",
        discovery_begin_date=date(2021, 4, 1),
        discovery_end_date=date(2021, 7, 29),
        period_start=date(2021, 1, 1),
        period_end=date(2021, 3, 31),
        parser_id="skhynix_opendart_periodic_product_revenue_v1",
        expected_identity_anchors=("DRAM", "NAND"),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND",),
            "other_products_services": ("기타",),
            "reported_company_revenue": ("합계",),
        },
    )
    mapping = PITPanelExpansionMapping(
        source_period="2021Q1",
        target_period="2021Q2",
        report_code="11013",
        expected_receipt=receipt,
    )
    metrics = ProductRevenueMetrics(
        unit="KRW_million",
        dram_total=60.0,
        nand_and_solutions=30.0,
        other_products_services=10.0,
        reported_company_revenue=100.0,
        direct_sum=100.0,
        reconciliation_delta=0.0,
    )
    archive_bytes = b"immutable-opendart-zip"
    text = "immutable normalized text"
    document = SimpleNamespace(
        rcept_no=receipt,
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        archive_bytes=len(archive_bytes),
        text_truncated=False,
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        text_chars=len(text),
        retrieved_at=datetime(2026, 8, 21, 3, 31, tzinfo=UTC),
    )
    archive = SimpleNamespace(archive_bytes=archive_bytes, evidence=document)
    discovery = SimpleNamespace(
        spec=spec,
        rcept_no=receipt,
        report_name=spec.report_name_exact,
        receipt_date=receipt_date,
    )

    monkeypatch.setattr(replay, "discover_periodic_product_revenue", lambda *_args: discovery)
    monkeypatch.setattr(
        replay,
        "OpenDartDisclosureDocumentClient",
        lambda _client: SimpleNamespace(document_with_archive=lambda _receipt: archive),
    )

    def _source_consensus(
        *,
        spec: PeriodicProductRevenueSpec,
        text: str,
        archive_bytes: bytes,
    ) -> ProductRevenueMetrics:
        assert spec.document_id == "skhynix_000660_2021q1_ex_ante_pit_expansion"
        assert text == "immutable normalized text"
        assert archive_bytes == b"immutable-opendart-zip"
        return metrics

    monkeypatch.setattr(
        replay,
        "parse_periodic_product_revenue_source_consensus",
        _source_consensus,
    )
    monkeypatch.setattr(
        replay,
        "bind_periodic_product_revenue_parser_contract",
        lambda *_args: {},
    )
    verified: list[object] = []

    def _verify(_pointer: object, *, evaluation_date: date) -> object:
        assert evaluation_date == date(2026, 8, 18)
        certification_path = next(tmp_path.glob("*__*/certification.json"))
        assert certification_path.is_file()
        verified.append(certification_path)
        return certification

    certification_holder: list[object] = []

    def _load(_pointer: object, *, evaluation_date: date) -> object:
        assert evaluation_date == date(2026, 8, 18)
        assert certification_holder
        return certification_holder[0]

    monkeypatch.setattr(replay, "load_periodic_product_revenue_certification", _load)

    original_class = replay.OpenDartPeriodicProductRevenueCertification

    def _construct(**kwargs: object) -> object:
        item = original_class(**kwargs)
        certification_holder.append(item)
        return item

    monkeypatch.setattr(replay, "OpenDartPeriodicProductRevenueCertification", _construct)

    certification, archive_path = replay._capture_product_source_for_replay(
        object(),
        spec,
        mapping,
        evaluation_date=evaluation_date,
        output=tmp_path,
    )

    assert certification.receipt_date == receipt_date
    assert certification.evaluation_date == evaluation_date
    assert archive_path.read_bytes() == archive_bytes
    pointer = (tmp_path / "latest_certification.json").read_text(encoding="utf-8")
    assert '"immutable_receipt_replay": true' in pointer
    assert '"retrieval_after_evaluation_date": true' in pointer
