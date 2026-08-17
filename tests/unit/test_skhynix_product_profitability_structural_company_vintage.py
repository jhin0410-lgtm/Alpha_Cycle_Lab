from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

import pytest

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    SecProductCycleDriverSupportEvidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    HistoricalProductRevenuePanelEvidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    QuarterlyCompanyProfitabilityEvidence,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    StructuralProfitabilityMethodContract,
    build_structural_rank_probe,
)

_EVALUATION_DATE = date(2026, 8, 17)
_HISTORICAL_EVIDENCE_ID = "a" * 64
_COMPANY_EVIDENCE_ID = "b" * 64
_CYCLE_EVIDENCE_ID = "c" * 64
_METHOD_MANIFEST_SHA = "d" * 64


def _rank_probe_inputs(
    *,
    company_evaluation_date: date,
    historical_evaluation_date: date = _EVALUATION_DATE,
) -> tuple[
    StructuralProfitabilityMethodContract,
    HistoricalProductRevenuePanelEvidence,
    QuarterlyCompanyProfitabilityEvidence,
    SecProductCycleDriverSupportEvidence,
]:
    method = cast(
        StructuralProfitabilityMethodContract,
        SimpleNamespace(
            ticker="000660",
            holdout_period="2026Q1",
            parameter_count=7,
            minimum_training_rows_for_rank_probe=7,
            method_id="skhynix_aggregate_direction_rank_probe",
            method_version="0.1-draft",
            manifest_sha256=_METHOD_MANIFEST_SHA,
        ),
    )
    historical = cast(
        HistoricalProductRevenuePanelEvidence,
        SimpleNamespace(
            ticker="000660",
            evaluation_date=historical_evaluation_date,
            evidence_id=_HISTORICAL_EVIDENCE_ID,
        ),
    )
    company = cast(
        QuarterlyCompanyProfitabilityEvidence,
        SimpleNamespace(
            ticker="000660",
            evaluation_date=company_evaluation_date,
            evidence_id=_COMPANY_EVIDENCE_ID,
            observations=(),
        ),
    )
    cycle = cast(
        SecProductCycleDriverSupportEvidence,
        SimpleNamespace(
            ticker="000660",
            observed_date=_EVALUATION_DATE,
            evidence_id=_CYCLE_EVIDENCE_ID,
            numeric_driver_values_available=False,
            observations=(),
        ),
    )
    return method, historical, company, cycle


@pytest.mark.parametrize(
    "company_evaluation_date",
    [date(2026, 8, 16), _EVALUATION_DATE],
)
def test_structural_rank_probe_accepts_non_future_company_vintage(
    company_evaluation_date: date,
) -> None:
    method, historical, company, cycle = _rank_probe_inputs(
        company_evaluation_date=company_evaluation_date
    )

    first = build_structural_rank_probe(
        method,
        historical,
        company,
        cycle,
        {},
        evaluation_date=_EVALUATION_DATE,
    )
    second = build_structural_rank_probe(
        method,
        historical,
        company,
        cycle,
        {},
        evaluation_date=_EVALUATION_DATE,
    )

    assert first.company_profitability_evidence_id == _COMPANY_EVIDENCE_ID
    assert first.evidence_id == second.evidence_id
    assert first.evaluation_date == _EVALUATION_DATE
    assert first.row_count == 0
    assert first.block_reason == "insufficient_aligned_training_rows"


def test_structural_rank_probe_rejects_future_company_vintage() -> None:
    method, historical, company, cycle = _rank_probe_inputs(
        company_evaluation_date=date(2026, 8, 18)
    )

    with pytest.raises(ValueError, match="future company profitability evidence"):
        build_structural_rank_probe(
            method,
            historical,
            company,
            cycle,
            {},
            evaluation_date=_EVALUATION_DATE,
        )


def test_structural_rank_probe_keeps_historical_panel_exact_date_contract() -> None:
    method, historical, company, cycle = _rank_probe_inputs(
        company_evaluation_date=date(2026, 8, 16),
        historical_evaluation_date=date(2026, 8, 16),
    )

    with pytest.raises(ValueError, match="historical evidence evaluation date mismatch"):
        build_structural_rank_probe(
            method,
            historical,
            company,
            cycle,
            {},
            evaluation_date=_EVALUATION_DATE,
        )
