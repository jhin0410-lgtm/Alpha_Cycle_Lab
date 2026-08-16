"""Offline replay of preserved SK hynix historical product-revenue parser failures.

This module re-runs the current production parser dispatch over already preserved,
hash-verified normalized text and OpenDART ZIP bytes. It is diagnostic only: successful
replay demonstrates parser compatibility with preserved evidence but does not create a
new source certification or promote any value into forecasting or valuation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
)
from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_parser_dispatch import (
    parse_periodic_product_revenue_archive,
    parse_periodic_product_revenue_text,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
)


def _metrics_dict(metrics: ProductRevenueMetrics | None) -> dict[str, object] | None:
    return None if metrics is None else asdict(metrics)


@dataclass(frozen=True)
class HistoricalProductRevenueFailureReplay:
    period_id: str
    text_parse_succeeded: bool
    archive_parse_succeeded: bool
    parser_agreement: bool
    text_error: str | None
    archive_error: str | None
    text_metrics: dict[str, object] | None
    archive_metrics: dict[str, object] | None
    replay_recoverable: bool
    network_requested: bool = False
    source_fact_promoted: bool = False
    certification_created: bool = False
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if self.replay_recoverable != (
            self.text_parse_succeeded
            and self.archive_parse_succeeded
            and self.parser_agreement
        ):
            raise ValueError("Historical failure replay recoverability flag is inconsistent")
        if self.network_requested or self.source_fact_promoted or self.certification_created:
            raise ValueError("Historical failure replay exceeds its diagnostic trust boundary")
        if (
            self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Historical failure replay exceeds downstream trust boundary")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def replay_historical_product_revenue_failure(
    diagnostic: HistoricalProductRevenueFailureDiagnostic,
    spec: PeriodicProductRevenueSpec,
) -> HistoricalProductRevenueFailureReplay:
    """Replay one verified preserved failure through current text and archive parsers."""

    text = Path(diagnostic.normalized_text_path).read_bytes().decode("utf-8")
    archive_bytes = Path(diagnostic.archive_path).read_bytes()

    text_metrics: ProductRevenueMetrics | None = None
    archive_metrics: ProductRevenueMetrics | None = None
    text_error: str | None = None
    archive_error: str | None = None

    try:
        text_metrics = parse_periodic_product_revenue_text(spec, text)
    except ValueError as exc:
        text_error = str(exc)

    try:
        archive_metrics = parse_periodic_product_revenue_archive(spec, archive_bytes)
    except ValueError as exc:
        archive_error = str(exc)

    agreement = (
        text_metrics is not None
        and archive_metrics is not None
        and text_metrics == archive_metrics
    )
    return HistoricalProductRevenueFailureReplay(
        period_id=diagnostic.period_id,
        text_parse_succeeded=text_metrics is not None,
        archive_parse_succeeded=archive_metrics is not None,
        parser_agreement=agreement,
        text_error=text_error,
        archive_error=archive_error,
        text_metrics=_metrics_dict(text_metrics),
        archive_metrics=_metrics_dict(archive_metrics),
        replay_recoverable=agreement,
    )


__all__ = [
    "HistoricalProductRevenueFailureReplay",
    "replay_historical_product_revenue_failure",
]
