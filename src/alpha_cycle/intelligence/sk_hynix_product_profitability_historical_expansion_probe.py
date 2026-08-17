"""Isolated live probe for pre-2023 SK hynix direct product-revenue candidates.

The probe writes only to a dedicated research output. It never modifies the canonical
2023+ historical panel or marks a frontier candidate as certified. Existing parser labels
and semantics are borrowed as a test hypothesis and must succeed on archived source bytes
before any later registry promotion is considered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_capture import (
    capture_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    load_periodic_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_frontier import (
    HistoricalExpansionCandidate,
    HistoricalExpansionFrontier,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT = Path(
    "data/private/research/skhynix-profitability-historical-expansion-probe"
)
DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY = Path(
    "config/skhynix_opendart_historical_product_revenue.yaml"
)


@dataclass(frozen=True)
class ProductRevenueProbePeriodResult:
    period_id: str
    success: bool
    artifact_pointer: str | None
    error_type: str | None
    error: str | None
    canonical_panel_modified: bool = False
    frontier_promoted: bool = False

    def __post_init__(self) -> None:
        if self.success != (self.artifact_pointer is not None):
            raise ValueError("Expansion probe success/pointer state is inconsistent")
        if self.success and (self.error_type is not None or self.error is not None):
            raise ValueError("Successful expansion probe cannot retain an error")
        if not self.success and (self.error_type is None or self.error is None):
            raise ValueError("Failed expansion probe must retain its error")
        if self.canonical_panel_modified or self.frontier_promoted:
            raise ValueError("Expansion probe exceeded its isolated trust boundary")


def frontier_product_revenue_spec(
    candidate: HistoricalExpansionCandidate,
    template: PeriodicProductRevenueSpec,
) -> PeriodicProductRevenueSpec:
    if template.ticker != "000660" or template.source_id != "opendart":
        raise ValueError("Expansion probe template must be SK hynix OpenDART")
    return PeriodicProductRevenueSpec(
        document_id=f"skhynix_000660_{candidate.period_id.casefold()}_product_revenue_probe",
        ticker=template.ticker,
        issuer_name=template.issuer_name,
        source_id=template.source_id,
        report_name_exact=candidate.opendart_report_name_exact,
        discovery_begin_date=candidate.opendart_discovery_begin_date,
        discovery_end_date=candidate.opendart_discovery_end_date,
        period_start=candidate.period_start,
        period_end=candidate.period_end,
        parser_id=template.parser_id,
        expected_identity_anchors=template.expected_identity_anchors,
        product_labels=template.product_labels,
    )


def load_product_revenue_probe_template(
    path: str | Path = DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
) -> PeriodicProductRevenueSpec:
    specs = load_periodic_product_revenue_registry(path)
    candidates = tuple(
        item
        for item in specs.values()
        if item.ticker == "000660"
        and item.parser_id == "skhynix_opendart_periodic_product_revenue_v1"
    )
    if not candidates:
        raise ValueError("Expansion probe could not find canonical parser template")
    first = candidates[0]
    signature = {
        (
            item.parser_id,
            item.expected_identity_anchors,
            tuple(sorted(item.product_labels.items())),
        )
        for item in candidates
    }
    if len(signature) != 1:
        raise ValueError("Canonical product-revenue parser templates are inconsistent")
    return first


def run_product_revenue_expansion_probe(
    client: OpenDartReadOnlyClient,
    frontier: HistoricalExpansionFrontier,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
    template_registry: str | Path = DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
) -> tuple[ProductRevenueProbePeriodResult, ...]:
    if evaluation_date < date(2022, 12, 1):
        raise ValueError("Expansion probe evaluation date predates candidate filing windows")
    template = load_product_revenue_probe_template(template_registry)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    results: list[ProductRevenueProbePeriodResult] = []
    for candidate in frontier.candidates:
        spec = frontier_product_revenue_spec(candidate, template)
        period_output = root / candidate.period_id
        try:
            capture_periodic_product_revenue_certification(
                client,
                spec,
                evaluation_date=evaluation_date,
                output=period_output,
            )
            pointer = period_output / "latest_certification.json"
            results.append(
                ProductRevenueProbePeriodResult(
                    period_id=candidate.period_id,
                    success=True,
                    artifact_pointer=str(pointer.resolve()),
                    error_type=None,
                    error=None,
                )
            )
        except Exception as exc:
            results.append(
                ProductRevenueProbePeriodResult(
                    period_id=candidate.period_id,
                    success=False,
                    artifact_pointer=None,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
    return tuple(results)


__all__ = [
    "DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT",
    "DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY",
    "ProductRevenueProbePeriodResult",
    "frontier_product_revenue_spec",
    "load_product_revenue_probe_template",
    "run_product_revenue_expansion_probe",
]
