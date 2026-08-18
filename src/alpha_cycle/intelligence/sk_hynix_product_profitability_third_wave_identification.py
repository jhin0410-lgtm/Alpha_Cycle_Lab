"""Preflight structural identification after the 2017Q1-2018Q3 source expansion.

This module does not fit a model. It combines the original fifteen v1 training rows with six
source-complete third-wave rows and reports whether the seven-column direction-regime design
is algebraically identifiable before any replacement estimator is registered. The already
spent 2026Q1 v1 holdout is evaluated separately as contaminated development data, never as a
new unseen observation.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np

from alpha_cycle.intelligence.sk_hynix_product_profitability_logit_margin_fit import (
    LogitMarginTrainingRow,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_closeout import (
    ThirdWaveCloseout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_frontier import (
    ThirdWaveFrontier,
)

_PARAMETER_COUNT = 7
_SPENT_HOLDOUT = "2026Q1"
_FUTURE_HOLDOUT = "2026Q3"


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _sign(value: float) -> float:
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0


def _condition(matrix: np.ndarray) -> float | None:
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms == 0.0):
        return None
    value = float(np.linalg.cond(matrix / norms))
    return value if math.isfinite(value) else None


def _regime(asp: float, bit: float) -> str:
    return f"asp={asp:+.0f},bit={bit:+.0f}"


@dataclass(frozen=True)
class IdentificationRow:
    period_id: str
    source_group: str
    company_revenue_krw_million: float
    company_gross_profit_krw_million: float
    dram_revenue_krw_million: float
    nand_revenue_krw_million: float
    other_revenue_krw_million: float
    dram_asp_direction_code: float
    dram_bit_volume_direction_code: float
    nand_asp_direction_code: float
    nand_bit_volume_direction_code: float
    company_product_revenue_reconciled: bool

    def __post_init__(self) -> None:
        if self.source_group not in {
            "v1_training_reuse",
            "third_wave_exact_numeric_downcast",
            "spent_v1_holdout_development",
        }:
            raise ValueError("Identification row source group is invalid")
        if self.company_revenue_krw_million <= 0.0:
            raise ValueError("Identification row company revenue must be positive")
        if min(
            self.dram_revenue_krw_million,
            self.nand_revenue_krw_million,
            self.other_revenue_krw_million,
        ) < 0.0:
            raise ValueError("Identification row product revenue cannot be negative")
        codes = (
            self.dram_asp_direction_code,
            self.dram_bit_volume_direction_code,
            self.nand_asp_direction_code,
            self.nand_bit_volume_direction_code,
        )
        if any(value not in {-1.0, 0.0, 1.0} for value in codes):
            raise ValueError("Identification row direction code is invalid")
        if not self.company_product_revenue_reconciled:
            raise ValueError("Identification row requires company/product reconciliation")

    @property
    def design_terms(self) -> tuple[float, ...]:
        dram = self.dram_revenue_krw_million
        nand = self.nand_revenue_krw_million
        return (
            dram,
            dram * self.dram_asp_direction_code,
            dram * self.dram_bit_volume_direction_code,
            nand,
            nand * self.nand_asp_direction_code,
            nand * self.nand_bit_volume_direction_code,
            self.other_revenue_krw_million,
        )


@dataclass(frozen=True)
class PanelIdentificationDiagnostic:
    panel_id: str
    row_count: int
    parameter_count: int
    residual_degrees_of_freedom: int
    design_rank: int
    full_column_rank: bool
    normalized_condition_number_report_only: float | None
    dram_regimes: tuple[str, ...]
    nand_regimes: tuple[str, ...]
    dram_revenue_share_range: tuple[float, float]
    nand_revenue_share_range: tuple[float, float]
    other_revenue_share_range: tuple[float, float]

    def __post_init__(self) -> None:
        if self.parameter_count != _PARAMETER_COUNT:
            raise ValueError("Identification panel parameter count drifted")
        if self.residual_degrees_of_freedom != self.row_count - self.parameter_count:
            raise ValueError("Identification panel residual DOF is inconsistent")
        if self.full_column_rank != (self.design_rank == self.parameter_count):
            raise ValueError("Identification panel rank flag is inconsistent")


@dataclass(frozen=True)
class ThirdWaveIdentificationPreflight:
    evidence_id: str
    evaluation_date: date
    frontier_evidence_id: str
    base_historical_row_count: int
    third_wave_row_count: int
    clean_historical_row_count: int
    contaminated_development_row_count: int
    exact_numeric_third_wave_driver_count: int
    company_product_revenue_reconciliation_certified: bool
    clean_historical_panel: PanelIdentificationDiagnostic
    contaminated_development_panel: PanelIdentificationDiagnostic
    preflight_ready_for_new_method_registration: bool
    fit_attempt_allowed: bool
    spent_2026q1_reused_as_unseen_holdout: bool
    future_holdout_period: str
    future_holdout_loaded: bool
    future_holdout_evaluated: bool
    block_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.frontier_evidence_id) != 64:
            raise ValueError("Identification preflight evidence ids must be SHA-256")
        if self.base_historical_row_count != 15 or self.third_wave_row_count != 6:
            raise ValueError("Identification preflight source row counts drifted")
        if self.clean_historical_row_count != 21:
            raise ValueError("Identification preflight clean panel must contain 21 rows")
        if self.contaminated_development_row_count != 22:
            raise ValueError("Identification preflight development panel must contain 22 rows")
        if self.exact_numeric_third_wave_driver_count != 24:
            raise ValueError("Identification preflight exact driver count drifted")
        expected_ready = (
            self.company_product_revenue_reconciliation_certified
            and self.clean_historical_panel.full_column_rank
            and self.contaminated_development_panel.full_column_rank
        )
        if self.preflight_ready_for_new_method_registration != expected_ready:
            raise ValueError("Identification preflight readiness flag is inconsistent")
        if self.fit_attempt_allowed:
            raise ValueError("Identification preflight cannot enable fit")
        if self.spent_2026q1_reused_as_unseen_holdout:
            raise ValueError("Identification preflight cannot reuse spent 2026Q1 as unseen")
        if self.future_holdout_period != _FUTURE_HOLDOUT:
            raise ValueError("Identification preflight future holdout drifted")
        if self.future_holdout_loaded or self.future_holdout_evaluated:
            raise ValueError("Identification preflight opened the future holdout")


def _from_logit_row(row: LogitMarginTrainingRow) -> IdentificationRow:
    total = (
        row.dram_revenue_krw_million
        + row.nand_revenue_krw_million
        + row.other_revenue_krw_million
    )
    return IdentificationRow(
        period_id=row.period_id,
        source_group=row.source_group,
        company_revenue_krw_million=row.company_revenue_krw_million,
        company_gross_profit_krw_million=row.company_gross_profit_krw_million,
        dram_revenue_krw_million=row.dram_revenue_krw_million,
        nand_revenue_krw_million=row.nand_revenue_krw_million,
        other_revenue_krw_million=row.other_revenue_krw_million,
        dram_asp_direction_code=row.dram_asp_direction_code,
        dram_bit_volume_direction_code=row.dram_bit_volume_direction_code,
        nand_asp_direction_code=row.nand_asp_direction_code,
        nand_bit_volume_direction_code=row.nand_bit_volume_direction_code,
        company_product_revenue_reconciled=(
            abs(total - row.company_revenue_krw_million) <= 1.0
        ),
    )


def _third_wave_rows(
    closeout: ThirdWaveCloseout,
    frontier: ThirdWaveFrontier,
) -> tuple[IdentificationRow, ...]:
    if not closeout.all_six_source_layers_complete:
        raise ValueError("Identification preflight requires six source-complete third-wave rows")
    candidate_by_period = {item.period_id: item for item in frontier.candidates}
    rows: list[IdentificationRow] = []
    for period in closeout.source.periods:
        company = period.company_observation
        recovery = period.product_recovery
        if company is None or recovery is None or recovery.observation is None:
            raise ValueError(
                f"Identification preflight lacks recovered third-wave row: {period.period_id}"
            )
        product = recovery.observation
        candidate = candidate_by_period[period.period_id]
        if product.rcept_no != company.rcept_no:
            raise ValueError("Identification preflight third-wave receipts diverged")
        drivers = candidate.drivers_qoq_percent
        rows.append(
            IdentificationRow(
                period_id=period.period_id,
                source_group="third_wave_exact_numeric_downcast",
                company_revenue_krw_million=company.revenue_krw / 1_000_000.0,
                company_gross_profit_krw_million=company.gross_profit_krw / 1_000_000.0,
                dram_revenue_krw_million=float(product.dram_revenue_million_krw),
                nand_revenue_krw_million=float(product.nand_revenue_million_krw),
                other_revenue_krw_million=float(product.other_revenue_million_krw),
                dram_asp_direction_code=_sign(drivers.dram_asp),
                dram_bit_volume_direction_code=_sign(drivers.dram_bit_volume),
                nand_asp_direction_code=_sign(drivers.nand_asp),
                nand_bit_volume_direction_code=_sign(drivers.nand_bit_volume),
                company_product_revenue_reconciled=(
                    product.total_revenue_million_krw * 1_000_000 == company.revenue_krw
                ),
            )
        )
    return tuple(rows)


def _panel(panel_id: str, rows: tuple[IdentificationRow, ...]) -> PanelIdentificationDiagnostic:
    matrix = np.asarray([row.design_terms for row in rows], dtype=float)
    rank = int(np.linalg.matrix_rank(matrix))
    shares = np.asarray(
        [
            (
                row.dram_revenue_krw_million / row.company_revenue_krw_million,
                row.nand_revenue_krw_million / row.company_revenue_krw_million,
                row.other_revenue_krw_million / row.company_revenue_krw_million,
            )
            for row in rows
        ],
        dtype=float,
    )
    return PanelIdentificationDiagnostic(
        panel_id=panel_id,
        row_count=len(rows),
        parameter_count=_PARAMETER_COUNT,
        residual_degrees_of_freedom=len(rows) - _PARAMETER_COUNT,
        design_rank=rank,
        full_column_rank=rank == _PARAMETER_COUNT,
        normalized_condition_number_report_only=_condition(matrix),
        dram_regimes=tuple(
            sorted({_regime(row.dram_asp_direction_code, row.dram_bit_volume_direction_code) for row in rows})
        ),
        nand_regimes=tuple(
            sorted({_regime(row.nand_asp_direction_code, row.nand_bit_volume_direction_code) for row in rows})
        ),
        dram_revenue_share_range=(float(np.min(shares[:, 0])), float(np.max(shares[:, 0]))),
        nand_revenue_share_range=(float(np.min(shares[:, 1])), float(np.max(shares[:, 1]))),
        other_revenue_share_range=(float(np.min(shares[:, 2])), float(np.max(shares[:, 2]))),
    )


def build_third_wave_identification_preflight(
    *,
    evaluation_date: date,
    base_v2_rows: tuple[LogitMarginTrainingRow, ...],
    closeout: ThirdWaveCloseout,
    frontier: ThirdWaveFrontier,
) -> ThirdWaveIdentificationPreflight:
    if tuple(row.period_id for row in base_v2_rows[-1:]) != (_SPENT_HOLDOUT,):
        raise ValueError("Identification preflight requires spent 2026Q1 as final development row")
    base_historical = tuple(_from_logit_row(row) for row in base_v2_rows[:-1])
    if len(base_historical) != 15:
        raise ValueError("Identification preflight requires the original fifteen historical rows")
    spent_q1 = _from_logit_row(base_v2_rows[-1])
    third = _third_wave_rows(closeout, frontier)
    clean_rows = third + base_historical
    development_rows = clean_rows + (spent_q1,)
    clean = _panel("clean_historical_21", clean_rows)
    development = _panel("contaminated_development_22", development_rows)
    reconciled = all(row.company_product_revenue_reconciled for row in development_rows)
    ready = reconciled and clean.full_column_rank and development.full_column_rank
    reasons: list[str] = []
    if not reconciled:
        reasons.append("company_product_revenue_reconciliation_failed")
    if not clean.full_column_rank:
        reasons.append("clean_21_row_direction_design_not_full_rank")
    if not development.full_column_rank:
        reasons.append("development_22_row_direction_design_not_full_rank")
    reasons.append("replacement_estimator_not_yet_preregistered")
    reasons.append("2026q3_future_holdout_remains_sealed")
    stable = {
        "evaluation_date": evaluation_date.isoformat(),
        "frontier_evidence_id": frontier.evidence_id,
        "clean_periods": [row.period_id for row in clean_rows],
        "development_periods": [row.period_id for row in development_rows],
        "clean": asdict(clean),
        "development": asdict(development),
        "reconciled": reconciled,
        "ready": ready,
    }
    return ThirdWaveIdentificationPreflight(
        evidence_id=_sha(stable),
        evaluation_date=evaluation_date,
        frontier_evidence_id=frontier.evidence_id,
        base_historical_row_count=len(base_historical),
        third_wave_row_count=len(third),
        clean_historical_row_count=len(clean_rows),
        contaminated_development_row_count=len(development_rows),
        exact_numeric_third_wave_driver_count=len(third) * 4,
        company_product_revenue_reconciliation_certified=reconciled,
        clean_historical_panel=clean,
        contaminated_development_panel=development,
        preflight_ready_for_new_method_registration=ready,
        fit_attempt_allowed=False,
        spent_2026q1_reused_as_unseen_holdout=False,
        future_holdout_period=_FUTURE_HOLDOUT,
        future_holdout_loaded=False,
        future_holdout_evaluated=False,
        block_reasons=tuple(reasons),
    )


__all__ = [
    "IdentificationRow",
    "PanelIdentificationDiagnostic",
    "ThirdWaveIdentificationPreflight",
    "build_third_wave_identification_preflight",
]
