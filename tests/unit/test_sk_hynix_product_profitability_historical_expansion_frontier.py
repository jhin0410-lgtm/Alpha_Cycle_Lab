from __future__ import annotations

from alpha_cycle.intelligence import (
    sk_hynix_product_profitability_historical_expansion_frontier as frontier_module,
)


def test_historical_expansion_frontier_is_exactly_six_fail_closed_candidates() -> None:
    frontier = frontier_module.load_historical_expansion_frontier()
    audit = frontier_module.audit_historical_expansion_frontier(frontier)

    assert tuple(item.period_id for item in frontier.candidates) == (
        "2021Q1",
        "2021Q2",
        "2021Q3",
        "2022Q1",
        "2022Q2",
        "2022Q3",
    )
    assert frontier.target_additional_training_rows == 6
    assert frontier.holdout_period == "2026Q1"
    assert frontier.q4_direct_quarter_derivation_allowed is False
    assert audit.candidate_count == 6
    assert audit.issuer_release_verified_count == 6
    assert audit.product_revenue_certified_count == 0
    assert audit.company_profitability_certified_count == 0
    assert audit.cycle_driver_certified_count == 0
    assert audit.source_layer_complete_count == 0
    assert audit.training_row_certified_count == 0
    assert audit.remaining_candidate_rows == 6
    assert audit.fit_enabled is False
    assert audit.holdout_evaluation_enabled is False


def test_historical_expansion_frontier_does_not_promote_newsroom_presence() -> None:
    frontier = frontier_module.load_historical_expansion_frontier()

    assert frontier.issuer_release_presence_is_training_row_evidence is False
    assert frontier.newsroom_release_is_product_revenue_certification is False
    assert frontier.qualitative_commentary_is_four_field_cycle_driver_certification is False
    assert frontier.candidate_registration_enables_fit is False
    assert frontier.candidate_registration_enables_holdout is False
    assert frontier.numeric_forecast_enabled is False
    assert frontier.fair_value_estimate_enabled is False
    assert frontier.target_price_enabled is False
    assert frontier.decision_score_enabled is False


def test_historical_expansion_open_dart_coordinates_are_quarter_specific() -> None:
    frontier = frontier_module.load_historical_expansion_frontier()
    expected = {
        "2021Q1": ("분기보고서 (2021.03)", "11013"),
        "2021Q2": ("반기보고서 (2021.06)", "11012"),
        "2021Q3": ("분기보고서 (2021.09)", "11014"),
        "2022Q1": ("분기보고서 (2022.03)", "11013"),
        "2022Q2": ("반기보고서 (2022.06)", "11012"),
        "2022Q3": ("분기보고서 (2022.09)", "11014"),
    }
    for candidate in frontier.candidates:
        report_name, report_code = expected[candidate.period_id]
        assert candidate.opendart_report_name_exact == report_name
        assert candidate.company_profitability_report_code == report_code
        assert candidate.product_parser_compatibility_status == "untested_historical_layout"
        assert candidate.training_row_status == "not_certified"
