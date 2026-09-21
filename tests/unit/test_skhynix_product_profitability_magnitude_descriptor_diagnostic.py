from __future__ import annotations

from datetime import date

from alpha_cycle.intelligence.sk_hynix_product_profitability_magnitude_descriptor_diagnostic import (
    build_magnitude_descriptor_diagnostic,
    classify_magnitude_descriptor,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    StructuralRankProbeResult,
    StructuralRankProbeRow,
    encode_direction_sign,
)


def _row(index: int) -> StructuralRankProbeRow:
    terms = tuple(1.0 if column == index else 0.0 for column in range(7))
    return StructuralRankProbeRow(
        period_id=f"202{3 + index // 4}Q{index % 4 + 1}",
        product_revenue_evidence_id=f"{index + 1:064x}",
        product_revenue_krw_million=100.0 + index,
        company_revenue_krw_million=100.0 + index,
        company_gross_profit_krw_million=10.0 + index,
        revenue_reconciliation_delta_krw=0,
        dram_revenue_krw_million=60.0,
        nand_revenue_krw_million=30.0,
        other_revenue_krw_million=10.0,
        dram_asp=encode_direction_sign("Around 20% Increase"),
        dram_bit_volume=encode_direction_sign("Over 70% Increase"),
        nand_asp=encode_direction_sign("Mid-high-teen% Increase"),
        nand_bit_volume=encode_direction_sign("Slight Decrease"),
        design_terms=terms,
    )


def _rank_probe() -> StructuralRankProbeResult:
    rows = tuple(_row(index) for index in range(7))
    periods = tuple(item.period_id for item in rows)
    return StructuralRankProbeResult(
        evidence_id="a" * 64,
        evaluation_date=date(2026, 8, 17),
        method_id="skhynix_aggregate_direction_rank_probe",
        method_version="0.1-draft",
        method_manifest_sha256="b" * 64,
        historical_product_revenue_evidence_id="c" * 64,
        company_profitability_evidence_id="d" * 64,
        cycle_driver_evidence_id="e" * 64,
        candidate_aligned_periods=(*periods, "2026Q1"),
        training_periods=periods,
        holdout_excluded_periods=("2026Q1",),
        reconciliation_failed_periods=(),
        rows=rows,
        row_count=7,
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


def test_literal_numeric_tokens_are_not_promoted_to_numeric_driver_facts() -> None:
    approximate = classify_magnitude_descriptor(
        period_id="2025Q1",
        driver_name="dram_asp",
        encoding=encode_direction_sign("Around 20% Increase"),
    )
    threshold = classify_magnitude_descriptor(
        period_id="2025Q1",
        driver_name="dram_bit_volume",
        encoding=encode_direction_sign("Over 70% Increase"),
    )
    literal = classify_magnitude_descriptor(
        period_id="2025Q1",
        driver_name="nand_asp",
        encoding=encode_direction_sign("12.5% Decrease"),
    )

    assert approximate.descriptor_kind == "approximate_percent_anchor"
    assert approximate.numeric_token_percent == 20.0
    assert threshold.descriptor_kind == "lower_threshold_percent"
    assert threshold.numeric_token_percent == 70.0
    assert literal.descriptor_kind == "literal_percent_text"
    assert literal.numeric_token_percent == 12.5
    for item in (approximate, threshold, literal):
        assert item.numeric_driver_source_fact is False
        assert item.model_numeric_value_assigned is False
        assert item.estimation_input_ready is False


def test_linguistic_and_qualitative_descriptors_preserve_text_without_midpoints() -> None:
    band = classify_magnitude_descriptor(
        period_id="2025Q1",
        driver_name="nand_asp",
        encoding=encode_direction_sign("Mid-high-teen% Increase"),
    )
    slight = classify_magnitude_descriptor(
        period_id="2025Q1",
        driver_name="nand_bit_volume",
        encoding=encode_direction_sign("Slight Decrease"),
    )
    flat = classify_magnitude_descriptor(
        period_id="2025Q1",
        driver_name="dram_asp",
        encoding=encode_direction_sign("Flat"),
    )

    assert band.descriptor_kind == "linguistic_percent_band"
    assert band.linguistic_band_label == "Mid-high-teen%"
    assert band.numeric_token_percent is None
    assert slight.descriptor_kind == "qualitative_only"
    assert slight.numeric_token_percent is None
    assert flat.descriptor_kind == "flat_direction_only"
    assert flat.numeric_token_percent is None


def test_unknown_direction_compatible_phrase_is_inventory_only_and_fail_closed() -> None:
    item = classify_magnitude_descriptor(
        period_id="2025Q1",
        driver_name="dram_asp",
        encoding=encode_direction_sign("Moderate Increase"),
    )
    assert item.descriptor_kind == "unclassified"
    assert item.numeric_token_percent is None
    assert item.estimation_input_ready is False


def test_full_rank_probe_builds_deterministic_inventory_but_does_not_open_fit() -> None:
    rank_probe = _rank_probe()
    first = build_magnitude_descriptor_diagnostic(
        rank_probe,
        source_rank_probe_pointer_sha256="f" * 64,
    )
    second = build_magnitude_descriptor_diagnostic(
        rank_probe,
        source_rank_probe_pointer_sha256="f" * 64,
    )

    assert first.evidence_id == second.evidence_id
    assert first.rank_probe_ready is True
    assert first.training_periods == rank_probe.training_periods
    assert first.observation_count == 28
    assert first.unique_source_text_count == 4
    assert dict(first.descriptor_kind_counts) == {
        "approximate_percent_anchor": 7,
        "linguistic_percent_band": 7,
        "lower_threshold_percent": 7,
        "qualitative_only": 7,
    }
    assert first.numeric_token_observation_count == 14
    assert first.unclassified_source_texts == ()
    assert first.all_descriptors_classified is True
    assert first.measurement_error_encoding_registered is False
    assert first.numeric_driver_source_facts_available is False
    assert first.model_numeric_values_assigned is False
    assert first.estimation_inputs_ready is False
    assert first.fit_attempt_allowed is False
    assert first.holdout_evaluation_allowed is False
    assert first.block_reason == "measurement_error_encoding_not_registered"
    assert first.numeric_forecast_enabled is False
    assert first.decision_score_enabled is False
