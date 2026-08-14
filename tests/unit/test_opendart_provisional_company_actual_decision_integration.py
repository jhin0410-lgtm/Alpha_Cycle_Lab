from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.decision_semiconductor_company_actual_calibrated import (
    _attach,
    _defaults,
)
from alpha_cycle.intelligence.expectation_gap_decision_evidence import (
    build_expectation_gap_decision_evidence,
)
from alpha_cycle.intelligence.opendart_provisional_earnings import ProvisionalEarningsMetrics
from alpha_cycle.intelligence.opendart_provisional_earnings_decision_evidence import (
    ProvisionalEarningsDecisionEvidence,
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


def _evidence() -> ProvisionalEarningsDecisionEvidence:
    return ProvisionalEarningsDecisionEvidence(
        evidence_id="a" * 64,
        evaluation_date=date(2026, 8, 14),
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


def test_missing_company_actual_is_explicitly_non_product_and_non_scoring() -> None:
    row = _defaults(_scorecard()).iloc[0]

    assert bool(row["opendart_provisional_company_actual_available"]) is False
    assert bool(row["opendart_provisional_product_baseline_eligible"]) is False
    assert bool(row["opendart_provisional_numeric_forecast_enabled"]) is False
    assert bool(row["opendart_provisional_decision_score_enabled"]) is False
    assert bool(row["semiconductor_baseline_reconciliation_certified"]) is False


def test_company_actual_does_not_promote_product_baseline_or_unlock_expectation_gap() -> None:
    attached = _attach(_scorecard(), _evidence())
    row = attached.iloc[0]

    assert bool(row["opendart_provisional_company_actual_available"]) is True
    assert row["opendart_provisional_revenue_krw_million"] == 79_318_746
    assert bool(row["opendart_provisional_product_baseline_eligible"]) is False
    assert bool(row["opendart_provisional_numeric_forecast_enabled"]) is False
    assert bool(row["opendart_provisional_decision_score_enabled"]) is False
    assert bool(row["semiconductor_baseline_reconciliation_certified"]) is False
    assert bool(row["semiconductor_assumption_baseline_reconciliation_certified"]) is False

    expectation = build_expectation_gap_decision_evidence(attached)
    expectation_row = expectation.rows.iloc[0]
    blockers = str(expectation_row["internal_forward_view_blockers_json"])

    assert "baseline_reconciliation_not_certified" in blockers
    assert expectation_row["expectation_gap_status"] == "blocked"
    assert bool(expectation_row["expectation_gap_enabled"]) is False
    assert bool(expectation_row["decision_score_enabled"]) is False
