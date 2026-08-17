from __future__ import annotations

from datetime import date

from alpha_cycle.intelligence.sk_hynix_product_profitability_promotion_readiness import (
    load_promotion_readiness_policy,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_acquisition import (
    SecondWaveCompanyObservation,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_closeout import (
    SecondWaveCloseout,
    SecondWaveCloseoutPeriod,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    load_second_wave_frontier,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_readiness import (
    build_second_wave_readiness,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    DirectionSignEncoding,
    StructuralRankProbeResult,
    StructuralRankProbeRow,
    load_structural_profitability_method,
)
from alpha_cycle.intelligence.sk_hynix_second_wave_product_revenue_recovery import (
    SecondWaveProductRecoveryResult,
    SecondWaveRecoveredProductRevenue,
)


def _flat() -> DirectionSignEncoding:
    return DirectionSignEncoding(source_text="Flat", direction="flat", code=0.0)


def _base_row(index: int, terms: tuple[float, ...]) -> StructuralRankProbeRow:
    return StructuralRankProbeRow(
        period_id=f"2023Q{(index % 3) + 1}-fixture-{index}",
        product_revenue_evidence_id=(f"{index + 1:x}" * 64)[:64],
        product_revenue_krw_million=1000.0 + index,
        company_revenue_krw_million=1000.0 + index,
        company_gross_profit_krw_million=300.0,
        revenue_reconciliation_delta_krw=0,
        dram_revenue_krw_million=600.0,
        nand_revenue_krw_million=300.0,
        other_revenue_krw_million=100.0,
        dram_asp=_flat(),
        dram_bit_volume=_flat(),
        nand_asp=_flat(),
        nand_bit_volume=_flat(),
        design_terms=terms,
    )


def _base_probe(method_hash: str) -> StructuralRankProbeResult:
    basis = [
        (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        (1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0),
    ]
    rows = tuple(_base_row(index, terms) for index, terms in enumerate(basis))
    return StructuralRankProbeResult(
        evidence_id="a" * 64,
        evaluation_date=date(2026, 8, 15),
        method_id="skhynix_aggregate_direction_rank_probe",
        method_version="0.1-draft",
        method_manifest_sha256=method_hash,
        historical_product_revenue_evidence_id="b" * 64,
        company_profitability_evidence_id="c" * 64,
        cycle_driver_evidence_id="d" * 64,
        candidate_aligned_periods=tuple(row.period_id for row in rows),
        training_periods=tuple(row.period_id for row in rows),
        holdout_excluded_periods=(),
        reconciliation_failed_periods=(),
        rows=rows,
        row_count=9,
        parameter_count=7,
        design_rank=7,
        full_column_rank=True,
        normalized_condition_number=1.0,
        company_product_revenue_reconciliation_certified=True,
        rank_probe_ready=True,
        fit_attempt_allowed=False,
        holdout_evaluation_allowed=False,
        block_reason="direction_only_rank_probe_not_estimation_method",
    )


def _closeout() -> SecondWaveCloseout:
    frontier = load_second_wave_frontier()
    periods = []
    for index, candidate in enumerate(frontier.candidates):
        receipt = f"20200{index + 1}01000001"[:14]
        total = 1000 + index * 10
        company = SecondWaveCompanyObservation(
            period_id=candidate.period_id,
            rcept_no=receipt,
            available_date=date(2020, min(index + 1, 12), 1),
            revenue_krw=total * 1_000_000,
            cost_of_sales_krw=(total - 300) * 1_000_000,
            gross_profit_krw=300 * 1_000_000,
            gross_margin_percent=300 / total * 100.0,
            raw_payload_sha256="e" * 64,
        )
        product = SecondWaveRecoveredProductRevenue(
            evidence_id=(f"{index + 2:x}" * 64)[:64],
            period_id=candidate.period_id,
            rcept_no=receipt,
            source_archive_sha256="f" * 64,
            member_name="fixture.xml",
            table_index=index,
            direct_quarter_column_index=1,
            direct_quarter_semantics="direct_quarter_3_month",
            dram_revenue_million_krw=600 + index * 5,
            nand_revenue_million_krw=300 + index * 3,
            other_revenue_million_krw=total - (900 + index * 8),
            total_revenue_million_krw=total,
            company_revenue_krw=total * 1_000_000,
        )
        recovery = SecondWaveProductRecoveryResult(
            period_id=candidate.period_id,
            certified=True,
            observation=product,
            candidate_reviews=(),
            structured_table_count=1,
            malformed_table_count=0,
            error=None,
        )
        periods.append(
            SecondWaveCloseoutPeriod(
                period_id=candidate.period_id,
                driver_numeric_source_certified=True,
                company_profitability_verified=True,
                company_recovery=None,
                company_observation=company,
                product_revenue_certified=True,
                product_recovery=recovery,
                source_layer_complete=True,
                company_error=None,
                product_error=None,
            )
        )
    return SecondWaveCloseout(
        periods=tuple(periods),
        company_profitability_verified_count=6,
        product_revenue_certified_count=6,
        driver_numeric_source_certified_count=6,
        source_layer_complete_count=6,
        all_six_source_layers_complete=True,
    )


def test_second_wave_combined_readiness_reaches_sample_depth_without_opening_fit() -> None:
    method = load_structural_profitability_method()
    policy = load_promotion_readiness_policy()
    readiness = build_second_wave_readiness(
        evaluation_date=date(2026, 8, 17),
        closeout=_closeout(),
        frontier=load_second_wave_frontier(),
        base_rank_probe=_base_probe(method.manifest_sha256),
        method=method,
        policy=policy,
    )

    assert readiness.base_row_count == 9
    assert readiness.second_wave_row_count == 6
    assert readiness.combined_row_count == 15
    assert readiness.required_training_rows == 15
    assert readiness.residual_degrees_of_freedom == 8
    assert readiness.sample_depth_gate_passed is True
    assert readiness.combined_design_rank == 7
    assert readiness.full_column_rank is True
    assert readiness.method_freeze_review_ready is True
    assert readiness.fit_attempt_allowed is False
    assert readiness.holdout_evaluation_allowed is False
    assert "mixed_driver_semantics_not_registered_for_estimation" in readiness.block_reasons
