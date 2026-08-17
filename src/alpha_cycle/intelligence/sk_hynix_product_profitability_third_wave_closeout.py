"""Acquire and close the 2017Q1-2018Q3 SK hynix exact-numeric source frontier.

The underlying OpenDART capture/recovery machinery is the same narrow, revenue-reconciled
path already proven on 2019-2020. This wrapper changes only the candidate frontier and output
roots. It does not promote rows, fit v1/v2, or reuse the spent 2026Q1 holdout as unseen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_closeout import (
    SecondWaveCloseout,
    run_second_wave_closeout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    SecondWaveFrontier,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_frontier import (
    ThirdWaveFrontier,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT = Path(
    "data/private/research/skhynix-product-profitability-third-wave-product-probe"
)
DEFAULT_THIRD_WAVE_COMPANY_OUTPUT = Path(
    "data/private/research/skhynix-product-profitability-third-wave-company-probe"
)
_EXPECTED_PERIODS = (
    "2017Q1",
    "2017Q2",
    "2017Q3",
    "2018Q1",
    "2018Q2",
    "2018Q3",
)


@dataclass(frozen=True)
class ThirdWaveCloseout:
    source: SecondWaveCloseout
    period_ids: tuple[str, ...]
    projected_v2_training_rows_if_all_promoted: int
    v1_refit_enabled: bool = False
    v2_fit_enabled: bool = False
    reuse_2026q1_as_unseen_holdout_for_v2_allowed: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if self.period_ids != _EXPECTED_PERIODS:
            raise ValueError("Third-wave closeout period order drifted")
        if tuple(item.period_id for item in self.source.periods) != self.period_ids:
            raise ValueError("Third-wave closeout source periods diverged")
        if self.projected_v2_training_rows_if_all_promoted != 21:
            raise ValueError("Third-wave projected v2 sample depth drifted")
        forbidden = (
            self.v1_refit_enabled,
            self.v2_fit_enabled,
            self.reuse_2026q1_as_unseen_holdout_for_v2_allowed,
            self.numeric_forecast_enabled,
            self.fair_value_estimate_enabled,
            self.target_price_enabled,
            self.decision_score_enabled,
        )
        if any(forbidden):
            raise ValueError("Third-wave closeout exceeded source-only boundary")

    @property
    def all_six_source_layers_complete(self) -> bool:
        return self.source.all_six_source_layers_complete

    @property
    def source_layer_complete_count(self) -> int:
        return self.source.source_layer_complete_count


def run_third_wave_closeout(
    client: OpenDartReadOnlyClient,
    frontier: ThirdWaveFrontier,
    *,
    evaluation_date: date,
    product_output: str | Path = DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT,
    company_output: str | Path = DEFAULT_THIRD_WAVE_COMPANY_OUTPUT,
) -> ThirdWaveCloseout:
    if frontier.spent_v1_holdout_period != "2026Q1":
        raise ValueError("Third-wave closeout spent-holdout binding drifted")
    compatible = cast(SecondWaveFrontier, cast(object, frontier))
    source = run_second_wave_closeout(
        client,
        compatible,
        evaluation_date=evaluation_date,
        product_output=product_output,
        company_output=company_output,
    )
    period_ids = tuple(item.period_id for item in frontier.candidates)
    return ThirdWaveCloseout(
        source=source,
        period_ids=period_ids,
        projected_v2_training_rows_if_all_promoted=15 + len(period_ids),
    )


__all__ = [
    "DEFAULT_THIRD_WAVE_COMPANY_OUTPUT",
    "DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT",
    "ThirdWaveCloseout",
    "run_third_wave_closeout",
]
