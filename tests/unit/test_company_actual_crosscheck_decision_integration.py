from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.company_actual_crosscheck_decision_evidence import (
    build_company_actual_crosscheck,
)
from alpha_cycle.intelligence.decision_semiconductor_company_actual_crosscheck_calibrated import (
    _attach_crosscheck,
    _attach_sec,
)
from alpha_cycle.intelligence.expectation_gap_decision_evidence import (
    build_expectation_gap_decision_evidence,
)
from alpha_cycle.intelligence.opendart_provisional_earnings import ProvisionalEarningsMetrics
from alpha_cycle.intelligence.opendart_provisional_earnings_decision_evidence import (
    ProvisionalEarningsDecisionEvidence,
)
from alpha_cycle.intelligence.sec_company_actual import (
    SecCompanyActualEvidence,
    SecCompanyActualMetrics,
)

EVALUATION_DATE = date(2026, 8, 14)


def _opendart() -> ProvisionalEarningsDecisionEvidence:
    return ProvisionalEarningsDecisionEvidence(
        evidence_id="a" * 64,
        evaluation_date=EVALUATION_DATE,
        document_id="skhynix_000660_2026q2_provisional",
        ticker="000660",
        issuer_name="SK hynix",
        rcept_no="20260729800013",
        receipt_date=date(2026, 7, 29),
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        metrics=ProvisionalEarningsMetrics(
            unit="KRW_million",
            revenue=79_318_746,
            operating_income=60_542_608,
            net_income=93_922_593,
        ),
        text_sha256="b" * 64,
        archive_sha256="c" * 64,
    )


def _sec(*, revenue_delta: float = 0.0) -> SecCompanyActualEvidence:
    return SecCompanyActualEvidence(
        evidence_id="d" * 64,
        evaluation_date=EVALUATION_DATE,
        document_id="skhynix_000660_2026q2_sec_6k_actual",
        ticker="000660",
        issuer_name="SK hynix",
        accession_number="0001193125-26-321989",
        primary_document="d115239d6k.htm",
        filing_date=date(2026, 7, 29),
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        submissions_url="https://data.sec.gov/submissions/CIK0002120882.json",
        filing_url=(
            "https://www.sec.gov/Archives/edgar/data/2120882/"
            "000119312526321989/d115239d6k.htm"
        ),
        submissions_sha256="e" * 64,
        filing_sha256="f" * 64,
        metrics=SecCompanyActualMetrics(
            unit="KRW_million",
            revenue=79_318_746 + revenue_delta,
            operating_income=60_542_608,
            net_income=93_922_593,
        ),
    )


def _scorecard() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "semiconductor_baseline_reconciliation_certified": False,
                "semiconductor_assumption_baseline_reconciliation_certified": False,
                "semiconductor_assumption_all_scenario_assumptions_model_use_ready": True,
                "semiconductor_assumption_output_method_certified": True,
                "semiconductor_assumption_company_reconciliation_certified": True,
                "semiconductor_assumption_model_version_frozen": True,
                "kis_forward_evidence_available": False,
                "kis_estimate_snapshot_change_available": False,
            }
        ]
    )


def test_matching_opendart_and_sec_actuals_certify_only_company_level_crosscheck() -> None:
    crosscheck = build_company_actual_crosscheck(_opendart(), _sec())

    assert crosscheck.crosscheck_certified is True
    assert crosscheck.revenue_delta_krw_million == 0
    assert crosscheck.operating_income_delta_krw_million == 0
    assert crosscheck.net_income_delta_krw_million == 0
    assert crosscheck.product_baseline_eligible is False
    assert crosscheck.numeric_forecast_enabled is False
    assert crosscheck.decision_score_enabled is False


def test_crosscheck_mismatch_is_explicit_not_silently_certified() -> None:
    crosscheck = build_company_actual_crosscheck(_opendart(), _sec(revenue_delta=1.0))

    assert crosscheck.crosscheck_certified is False
    assert crosscheck.revenue_delta_krw_million == 1.0


def test_dual_official_company_actuals_do_not_unlock_product_baseline_or_expectation_gap() -> None:
    sec = _sec()
    crosscheck = build_company_actual_crosscheck(_opendart(), sec)
    scorecards = _attach_sec(_scorecard(), sec)
    scorecards = _attach_crosscheck(scorecards, crosscheck)
    row = scorecards.iloc[0]

    assert bool(row["sec_company_actual_available"]) is True
    assert bool(row["sec_company_actual_product_baseline_eligible"]) is False
    assert bool(row["company_actual_crosscheck_available"]) is True
    assert bool(row["company_actual_crosscheck_certified"]) is True
    assert bool(row["company_actual_crosscheck_product_baseline_eligible"]) is False
    assert bool(row["semiconductor_baseline_reconciliation_certified"]) is False
    assert bool(row["semiconductor_assumption_baseline_reconciliation_certified"]) is False

    expectation = build_expectation_gap_decision_evidence(scorecards)
    expectation_row = expectation.rows.iloc[0]
    blockers = str(expectation_row["internal_forward_view_blockers_json"])

    assert "baseline_reconciliation_not_certified" in blockers
    assert expectation_row["expectation_gap_status"] == "blocked"
    assert bool(expectation_row["expectation_gap_enabled"]) is False
    assert bool(expectation_row["decision_score_enabled"]) is False
