"""Close unresolved 2019-2020 SK hynix second-wave source layers in one pass."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_acquisition import (
    DEFAULT_SECOND_WAVE_COMPANY_OUTPUT,
    DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT,
    SecondWaveAcquisitionResult,
    SecondWaveCompanyObservation,
    run_second_wave_acquisition,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    SecondWaveFrontier,
)
from alpha_cycle.intelligence.sk_hynix_second_wave_company_name_recovery import (
    SecondWaveCompanyNameRecovery,
    recover_second_wave_company_by_exact_names,
)
from alpha_cycle.intelligence.sk_hynix_second_wave_product_revenue_recovery import (
    SecondWaveProductRecoveryResult,
    recover_failed_second_wave_product_revenue,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient


@dataclass(frozen=True)
class SecondWaveCloseoutPeriod:
    period_id: str
    driver_numeric_source_certified: bool
    company_profitability_verified: bool
    company_recovery: SecondWaveCompanyNameRecovery | None
    company_observation: SecondWaveCompanyObservation | None
    product_revenue_certified: bool
    product_recovery: SecondWaveProductRecoveryResult | None
    source_layer_complete: bool
    company_error: str | None
    product_error: str | None
    training_row_promoted: bool = False
    fit_enabled: bool = False
    holdout_evaluation_allowed: bool = False

    def __post_init__(self) -> None:
        expected = (
            self.driver_numeric_source_certified
            and self.company_profitability_verified
            and self.product_revenue_certified
        )
        if self.source_layer_complete != expected:
            raise ValueError("Second-wave closeout source-completion state is inconsistent")
        if self.company_profitability_verified != (self.company_observation is not None):
            raise ValueError("Second-wave closeout company state is inconsistent")
        if self.training_row_promoted or self.fit_enabled or self.holdout_evaluation_allowed:
            raise ValueError("Second-wave closeout exceeded source trust boundary")


@dataclass(frozen=True)
class SecondWaveCloseout:
    periods: tuple[SecondWaveCloseoutPeriod, ...]
    company_profitability_verified_count: int
    product_revenue_certified_count: int
    driver_numeric_source_certified_count: int
    source_layer_complete_count: int
    all_six_source_layers_complete: bool
    training_row_promoted: bool = False
    fit_enabled: bool = False
    holdout_evaluation_allowed: bool = False

    def __post_init__(self) -> None:
        if len(self.periods) != 6:
            raise ValueError("Second-wave closeout must retain six periods")
        if self.company_profitability_verified_count != sum(
            item.company_profitability_verified for item in self.periods
        ):
            raise ValueError("Second-wave closeout company count is inconsistent")
        if self.product_revenue_certified_count != sum(
            item.product_revenue_certified for item in self.periods
        ):
            raise ValueError("Second-wave closeout product count is inconsistent")
        if self.driver_numeric_source_certified_count != sum(
            item.driver_numeric_source_certified for item in self.periods
        ):
            raise ValueError("Second-wave closeout driver count is inconsistent")
        if self.source_layer_complete_count != sum(item.source_layer_complete for item in self.periods):
            raise ValueError("Second-wave closeout complete count is inconsistent")
        if self.all_six_source_layers_complete != (self.source_layer_complete_count == 6):
            raise ValueError("Second-wave closeout all-six flag is inconsistent")
        if self.training_row_promoted or self.fit_enabled or self.holdout_evaluation_allowed:
            raise ValueError("Second-wave closeout exceeded model boundary")


def _object(path: Path) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Second-wave company probe pointer is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Second-wave company probe pointer is invalid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("Second-wave company probe pointer must be an object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _raw_paths(company_output: Path) -> dict[str, Path]:
    payload = _object(company_output / "latest_company_probe.json")
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("Second-wave company probe results must be an array")
    result: dict[str, Path] = {}
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        item = {str(key): value for key, value in cast(dict[object, object], raw).items()}
        path = item.get("raw_payload_path")
        if path:
            result[str(item.get("period_id", ""))] = Path(str(path))
    return result


def run_second_wave_closeout(
    client: OpenDartReadOnlyClient,
    frontier: SecondWaveFrontier,
    *,
    evaluation_date: date,
    product_output: str | Path = DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT,
    company_output: str | Path = DEFAULT_SECOND_WAVE_COMPANY_OUTPUT,
) -> SecondWaveCloseout:
    product_root = Path(product_output)
    company_root = Path(company_output)
    base = run_second_wave_acquisition(
        client,
        frontier,
        evaluation_date=evaluation_date,
        product_output=product_root,
        company_output=company_root,
    )
    base_by_period: dict[str, SecondWaveAcquisitionResult] = {
        item.period_id: item for item in base
    }
    raw_paths = _raw_paths(company_root)
    periods: list[SecondWaveCloseoutPeriod] = []

    for candidate in frontier.candidates:
        base_item = base_by_period[candidate.period_id]
        company_observation = base_item.company_observation
        company_recovery: SecondWaveCompanyNameRecovery | None = None
        company_error = base_item.company_error
        if company_observation is None and candidate.period_id in raw_paths:
            try:
                company_recovery = recover_second_wave_company_by_exact_names(
                    candidate,
                    raw_paths[candidate.period_id],
                    evaluation_date=evaluation_date,
                )
                company_observation = company_recovery.observation
                company_error = None
            except ValueError as exc:
                company_error = str(exc)

        product_recovery = base_item.product_recovery
        product_certified = base_item.product_revenue_certified
        product_error = base_item.product_probe_error
        if not product_certified and company_observation is not None:
            try:
                product_recovery = recover_failed_second_wave_product_revenue(
                    candidate.period_id,
                    product_root / candidate.period_id,
                    company_revenue_krw=company_observation.revenue_krw,
                    company_rcept_no=company_observation.rcept_no,
                )
                product_certified = product_recovery.certified
                product_error = product_recovery.error
            except ValueError as exc:
                product_error = str(exc)

        company_verified = company_observation is not None
        complete = (
            base_item.driver_four_field_numeric_source_certified
            and company_verified
            and product_certified
        )
        periods.append(
            SecondWaveCloseoutPeriod(
                period_id=candidate.period_id,
                driver_numeric_source_certified=(
                    base_item.driver_four_field_numeric_source_certified
                ),
                company_profitability_verified=company_verified,
                company_recovery=company_recovery,
                company_observation=company_observation,
                product_revenue_certified=product_certified,
                product_recovery=product_recovery,
                source_layer_complete=complete,
                company_error=company_error,
                product_error=product_error,
            )
        )

    result = SecondWaveCloseout(
        periods=tuple(periods),
        company_profitability_verified_count=sum(
            item.company_profitability_verified for item in periods
        ),
        product_revenue_certified_count=sum(item.product_revenue_certified for item in periods),
        driver_numeric_source_certified_count=sum(
            item.driver_numeric_source_certified for item in periods
        ),
        source_layer_complete_count=sum(item.source_layer_complete for item in periods),
        all_six_source_layers_complete=all(item.source_layer_complete for item in periods),
    )
    report = {
        "status": "skhynix_product_profitability_second_wave_closeout_completed",
        "evaluation_date": evaluation_date.isoformat(),
        "frontier_evidence_id": frontier.evidence_id,
        "closeout": asdict(result),
        "training_row_promoted": False,
        "fit_enabled": False,
        "holdout_evaluation_allowed": False,
    }
    company_root.mkdir(parents=True, exist_ok=True)
    (company_root / "latest_second_wave_closeout.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return result


__all__ = [
    "SecondWaveCloseout",
    "SecondWaveCloseoutPeriod",
    "run_second_wave_closeout",
]
