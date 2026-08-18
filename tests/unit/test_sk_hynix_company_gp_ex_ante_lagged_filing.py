from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    load_ex_ante_feature_frontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_lagged_filing import (
    LaggedFilingSourceRecord,
    certify_lagged_filing_records,
    certify_lagged_filing_source_record,
    load_lagged_filing_certification_contract,
    persist_locked_pit_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    load_point_in_time_feature_bundle,
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


def _record(
    tmp_path: Path,
    *,
    source_period: str,
    target_period: str,
    receipt_date: date,
    suffix: str,
) -> LaggedFilingSourceRecord:
    rcept_no = receipt_date.strftime("%Y%m%d") + suffix.zfill(6)
    raw_object = {
        "financials": {
            "list": [
                {
                    "rcept_no": rcept_no,
                    "account_id": "Revenue",
                    "thstrm_amount": "1000000000",
                },
                {
                    "rcept_no": rcept_no,
                    "account_id": "GrossProfit",
                    "thstrm_amount": "400000000",
                },
            ]
        },
        "period_id": source_period,
    }
    raw_path = tmp_path / f"{source_period}_company.json"
    raw_path.write_text(
        json.dumps(raw_object, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    archive_bytes = f"archive:{source_period}".encode()
    archive_path = tmp_path / f"{source_period}_product.zip"
    archive_path.write_bytes(archive_bytes)
    return LaggedFilingSourceRecord(
        source_period=source_period,
        target_period=target_period,
        rcept_no=rcept_no,
        receipt_date=receipt_date,
        company_revenue_krw=1_000_000_000,
        company_gross_profit_krw=400_000_000,
        company_raw_payload_sha256=_sha(raw_object),
        company_raw_path=str(raw_path),
        product_evidence_id=hashlib.sha256(
            f"product:{source_period}".encode()
        ).hexdigest(),
        product_archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        product_archive_path=str(archive_path),
        nand_revenue_krw_million=300.0,
        other_revenue_krw_million=50.0,
        product_total_revenue_krw_million=1000.0,
    )


def test_lagged_filing_contract_freezes_14_q2_q3_rows() -> None:
    contract = load_lagged_filing_certification_contract()

    assert contract.expected_target_row_count == 14
    assert contract.expected_feature_observation_count == 70
    assert len(contract.expected_source_periods) == 14
    assert len(contract.expected_target_periods) == 14
    assert all(not period.endswith("Q1") for period in contract.expected_target_periods)
    assert contract.target_by_source["2017Q1"] == "2017Q2"
    assert contract.target_by_source["2017Q2"] == "2017Q3"
    assert not contract.target_join_allowed
    assert not contract.estimator_fit_allowed


def test_single_lagged_filing_record_certifies_five_features(tmp_path: Path) -> None:
    contract = load_lagged_filing_certification_contract()
    protocol = load_frozen_company_gp_ex_ante_protocol()
    record = _record(
        tmp_path,
        source_period="2025Q1",
        target_period="2025Q2",
        receipt_date=date(2025, 5, 15),
        suffix="1",
    )

    result = certify_lagged_filing_source_record(contract, protocol, record)

    assert result.certified
    assert tuple(item.feature_id for item in result.observations) == contract.feature_ids
    values = {item.feature_id: item.value for item in result.observations}
    assert values["lagged_company_revenue"] == pytest.approx(1000.0)
    assert values["lagged_company_gross_profit"] == pytest.approx(400.0)
    assert values["lagged_company_gross_margin"] == pytest.approx(0.4)
    assert values["lagged_nand_revenue_share"] == pytest.approx(0.3)
    assert values["lagged_other_revenue_share"] == pytest.approx(0.05)
    assert all(item.period_id == "2025Q2" for item in result.observations)
    assert not any(item.target_metric_in_payload for item in result.observations)


def test_lagged_filing_rejects_receipt_after_frozen_origin(tmp_path: Path) -> None:
    contract = load_lagged_filing_certification_contract()
    protocol = load_frozen_company_gp_ex_ante_protocol()
    record = _record(
        tmp_path,
        source_period="2025Q1",
        target_period="2025Q2",
        receipt_date=date(2025, 6, 1),
        suffix="1",
    )

    with pytest.raises(ValueError, match="unavailable by forecast origin"):
        certify_lagged_filing_source_record(contract, protocol, record)


def test_lagged_filing_rejects_source_target_mapping_drift(tmp_path: Path) -> None:
    contract = load_lagged_filing_certification_contract()
    protocol = load_frozen_company_gp_ex_ante_protocol()
    record = _record(
        tmp_path,
        source_period="2025Q1",
        target_period="2025Q3",
        receipt_date=date(2025, 5, 15),
        suffix="1",
    )

    with pytest.raises(ValueError, match="source-target mapping diverged"):
        certify_lagged_filing_source_record(contract, protocol, record)


def test_lagged_filing_rejects_company_or_product_byte_tampering(tmp_path: Path) -> None:
    contract = load_lagged_filing_certification_contract()
    protocol = load_frozen_company_gp_ex_ante_protocol()
    company_record = _record(
        tmp_path,
        source_period="2025Q1",
        target_period="2025Q2",
        receipt_date=date(2025, 5, 15),
        suffix="1",
    )
    Path(company_record.company_raw_path).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="company raw JSON canonical hash mismatch"):
        certify_lagged_filing_source_record(contract, protocol, company_record)

    product_record = _record(
        tmp_path,
        source_period="2025Q2",
        target_period="2025Q3",
        receipt_date=date(2025, 8, 15),
        suffix="2",
    )
    Path(product_record.product_archive_path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="product archive SHA-256 mismatch"):
        certify_lagged_filing_source_record(contract, protocol, product_record)


def test_complete_14_row_bundle_is_70_of_70_pit_eligible(tmp_path: Path) -> None:
    contract = load_lagged_filing_certification_contract()
    protocol = load_frozen_company_gp_ex_ante_protocol()
    frontier = load_ex_ante_feature_frontier()
    records: list[LaggedFilingSourceRecord] = []
    for index, (source_period, target_period) in enumerate(
        contract.source_to_target_mapping,
        start=1,
    ):
        year = int(source_period[:4])
        source_quarter = int(source_period[-1])
        receipt = date(year, 5, 15) if source_quarter == 1 else date(year, 8, 15)
        records.append(
            _record(
                tmp_path,
                source_period=source_period,
                target_period=target_period,
                receipt_date=receipt,
                suffix=str(index),
            )
        )

    result, bundle = certify_lagged_filing_records(
        contract,
        protocol,
        frontier,
        tuple(records),
        created_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
    )

    assert result.completion_gate_passed
    assert result.certified_target_row_count == 14
    assert result.feature_observation_count == 70
    assert result.pit_audit.eligible_observation_count == 70
    assert result.pit_audit.rejected_observation_count == 0
    assert result.pit_audit.all_observations_point_in_time_eligible
    assert not result.target_values_included
    assert not result.target_join_allowed
    assert not result.estimator_fit_allowed
    assert not result.first_pit_backtest_run
    assert not result.q3_target_read
    assert not result.q3_source_outcome_loaded

    path = tmp_path / "bundle.json"
    persist_locked_pit_feature_bundle(bundle, path)
    reloaded = load_point_in_time_feature_bundle(path)
    assert reloaded.evidence_id == bundle.evidence_id
    assert len(reloaded.observations) == 70
