from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    load_ex_ante_feature_frontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_lagged_filing import (
    LaggedFilingSourceRecord,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_expansion import (
    ExpansionSourceAttempt,
    build_expansion_product_spec,
    certify_expansion_source_record,
    load_frozen_pit_panel_expansion_contract,
    select_first_complete_legacy_year,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    load_frozen_company_gp_ex_ante_protocol,
)


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _attempt(source_period: str, target_period: str, *, success: bool) -> ExpansionSourceAttempt:
    return ExpansionSourceAttempt(
        source_period=source_period,
        target_period=target_period,
        success=success,
        receipt_no="20160516000001" if success else None,
        receipt_date="2016-05-16" if success else None,
        company_raw_bytes_sha256="a" * 64 if success else None,
        product_archive_sha256="b" * 64 if success else None,
        error_type=None if success else "ValueError",
        error=None if success else "source unavailable",
    )


def test_frozen_expansion_contract_preserves_source_only_selection() -> None:
    contract = load_frozen_pit_panel_expansion_contract()

    assert contract.fixed_mappings[0].source_period == "2021Q1"
    assert contract.fixed_mappings[-1].source_period == "2022Q2"
    assert contract.legacy_year_priority == (2016, 2015, 2014)
    assert contract.required_total_rows == 20
    assert contract.required_total_observations == 100
    assert contract.discovery_window_days == 120


def test_product_spec_uses_frozen_deterministic_window() -> None:
    contract = load_frozen_pit_panel_expansion_contract()
    mapping = contract.fixed_mappings[0]

    spec = build_expansion_product_spec(contract, mapping)

    assert spec.report_name_exact == "분기보고서 (2021.03)"
    assert spec.period_start == date(2021, 1, 1)
    assert spec.period_end == date(2021, 3, 31)
    assert spec.discovery_begin_date == date(2021, 4, 1)
    assert spec.discovery_end_date == date(2021, 7, 29)


def test_legacy_selection_uses_first_complete_frozen_year_pair_only() -> None:
    contract = load_frozen_pit_panel_expansion_contract()
    attempts = (
        _attempt("2016Q1", "2016Q2", success=True),
        _attempt("2016Q2", "2016Q3", success=False),
        _attempt("2015Q1", "2015Q2", success=True),
        _attempt("2015Q2", "2015Q3", success=True),
    )

    assert select_first_complete_legacy_year(contract, attempts) == 2015


def test_legacy_selection_never_accepts_partial_year() -> None:
    contract = load_frozen_pit_panel_expansion_contract()
    attempts = (
        _attempt("2016Q1", "2016Q2", success=True),
        _attempt("2016Q2", "2016Q3", success=False),
        _attempt("2015Q1", "2015Q2", success=False),
        _attempt("2015Q2", "2015Q3", success=True),
        _attempt("2014Q1", "2014Q2", success=True),
        _attempt("2014Q2", "2014Q3", success=False),
    )

    assert select_first_complete_legacy_year(contract, attempts) is None


def test_expansion_source_certification_stays_target_blind(tmp_path: Path) -> None:
    protocol = load_frozen_company_gp_ex_ante_protocol()
    frontier = load_ex_ante_feature_frontier()
    company_payload = {"source": "immutable filing", "period": "2016Q1"}
    company_path = tmp_path / "company.json"
    company_path.write_text(
        json.dumps(company_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    product_path = tmp_path / "product.zip"
    product_bytes = b"preserved-product-archive"
    product_path.write_bytes(product_bytes)
    record = LaggedFilingSourceRecord(
        source_period="2016Q1",
        target_period="2016Q2",
        rcept_no="20160516000001",
        receipt_date=date(2016, 5, 16),
        company_revenue_krw=100_000_000,
        company_gross_profit_krw=40_000_000,
        company_raw_payload_sha256=_sha(company_payload),
        company_raw_path=str(company_path),
        product_evidence_id="c" * 64,
        product_archive_sha256=hashlib.sha256(product_bytes).hexdigest(),
        product_archive_path=str(product_path),
        nand_revenue_krw_million=30.0,
        other_revenue_krw_million=10.0,
        product_total_revenue_krw_million=100.0,
    )

    certified = certify_expansion_source_record(protocol, frontier, record)

    assert certified.target_period == "2016Q2"
    assert certified.target_read is False
    assert certified.feature_ids == (
        "lagged_company_revenue",
        "lagged_company_gross_profit",
        "lagged_company_gross_margin",
        "lagged_nand_revenue_share",
        "lagged_other_revenue_share",
    )
    assert len(certified.observations) == 5
    assert all(
        item.provenance_class == "timestamped_immutable_filing"
        for item in certified.observations
    )
    assert all(item.target_metric_in_payload is False for item in certified.observations)
