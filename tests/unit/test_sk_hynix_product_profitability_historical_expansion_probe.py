from __future__ import annotations

import pytest

from alpha_cycle.intelligence import (
    sk_hynix_product_profitability_historical_expansion_frontier as frontier_module,
)
from alpha_cycle.intelligence import (
    sk_hynix_product_profitability_historical_expansion_probe as probe_module,
)


def test_frontier_candidate_builds_isolated_existing_parser_probe_spec() -> None:
    frontier = frontier_module.load_historical_expansion_frontier()
    template = probe_module.load_product_revenue_probe_template()
    candidate = frontier.candidates[0]

    spec = probe_module.frontier_product_revenue_spec(candidate, template)

    assert spec.document_id == "skhynix_000660_2021q1_product_revenue_probe"
    assert spec.report_name_exact == "분기보고서 (2021.03)"
    assert spec.period_start.isoformat() == "2021-01-01"
    assert spec.period_end.isoformat() == "2021-03-31"
    assert spec.parser_id == "skhynix_opendart_periodic_product_revenue_v1"
    assert spec.expected_identity_anchors == template.expected_identity_anchors
    assert spec.product_labels == template.product_labels


def test_probe_result_cannot_claim_success_without_artifact() -> None:
    with pytest.raises(ValueError, match="success/pointer"):
        probe_module.ProductRevenueProbePeriodResult(
            period_id="2021Q1",
            success=True,
            artifact_pointer=None,
            error_type=None,
            error=None,
        )


def test_probe_result_never_promotes_canonical_state() -> None:
    item = probe_module.ProductRevenueProbePeriodResult(
        period_id="2021Q1",
        success=False,
        artifact_pointer=None,
        error_type="ValueError",
        error="diagnostic-only",
    )

    assert item.canonical_panel_modified is False
    assert item.frontier_promoted is False
