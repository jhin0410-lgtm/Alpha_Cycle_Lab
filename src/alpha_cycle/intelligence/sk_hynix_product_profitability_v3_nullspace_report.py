"""Bind the V3 nullspace math diagnostic to an existing private V3 fit report."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import numpy as np

from alpha_cycle.intelligence.sk_hynix_product_profitability_v3_nullspace_math import (
    PARAMETER_NAMES,
    JacobianDecomposition,
    build_jacobian,
    decompose_jacobian,
)

_EXPECTED_STATUS = "skhynix_product_profitability_v3_expanded_logit_margin_fit_completed"
_EXPECTED_METHOD_VERSION = "3.0-frozen-pre-fit"


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"V3 nullspace {label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _items(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"V3 nullspace {label} must be an array")
    return list(value)


def _number(item: dict[str, object], key: str) -> float:
    return float(str(item.get(key, "nan")))


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


def _row_matrix(rows: list[object]) -> tuple[tuple[str, ...], np.ndarray]:
    periods: list[str] = []
    matrix: list[tuple[float, ...]] = []
    for raw in rows:
        item = _mapping(raw, "training row")
        period = str(item.get("period_id", ""))
        if not period:
            raise ValueError("V3 nullspace training period is empty")
        revenue = _number(item, "company_revenue_krw_million")
        dram = _number(item, "dram_revenue_krw_million")
        nand = _number(item, "nand_revenue_krw_million")
        other = _number(item, "other_revenue_krw_million")
        if abs(dram + nand + other - revenue) > 1.0:
            raise ValueError("V3 nullspace product/company revenue reconciliation failed")
        codes = (
            _number(item, "dram_asp_direction_code"),
            _number(item, "dram_bit_volume_direction_code"),
            _number(item, "nand_asp_direction_code"),
            _number(item, "nand_bit_volume_direction_code"),
        )
        if any(value not in {-1.0, 0.0, 1.0} for value in codes):
            raise ValueError("V3 nullspace direction code is invalid")
        periods.append(period)
        matrix.append((revenue, dram, nand, other, *codes))
    if len(periods) != len(set(periods)):
        raise ValueError("V3 nullspace training periods are not unique")
    return tuple(periods), np.asarray(matrix, dtype=float)


def _theta(value: object) -> np.ndarray:
    raw = _items(value, "parameters")
    if len(raw) != len(PARAMETER_NAMES):
        raise ValueError("V3 nullspace parameter count drifted")
    theta = np.asarray([float(str(item)) for item in raw], dtype=float)
    if not np.all(np.isfinite(theta)):
        raise ValueError("V3 nullspace parameters must be finite")
    return theta


@dataclass(frozen=True)
class FoldNullspaceDiagnostic:
    held_out_period: str
    jacobian_rank: int
    normalized_condition_number_report_only: float | None
    smallest_to_largest_ratio_report_only: float | None
    dominant_parameter_report_only: str


@dataclass(frozen=True)
class V3NullspaceReport:
    evidence_id: str
    source_fit_evidence_id: str
    method_evidence_id: str
    method_version: str
    row_count: int
    parameter_count: int
    linear_prefit_full_rank: bool
    full_fit: JacobianDecomposition
    rank_deficient_loocv_periods: tuple[str, ...]
    loocv_rank_deficient_count: int
    loocv_diagnostics_report_only: tuple[FoldNullspaceDiagnostic, ...]
    nonlinear_rank_loss_after_link_fit: bool
    replacement_model_selected: bool = False
    future_holdout_period: str = "2026Q3"
    future_holdout_loaded: bool = False
    future_holdout_evaluated: bool = False
    numeric_forward_forecast_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.source_fit_evidence_id) != 64:
            raise ValueError("V3 nullspace evidence ids must be SHA-256")
        if len(self.method_evidence_id) != 64:
            raise ValueError("V3 nullspace method evidence id must be SHA-256")
        if self.method_version != _EXPECTED_METHOD_VERSION:
            raise ValueError("V3 nullspace method version drifted")
        if (self.row_count, self.parameter_count) != (21, 7):
            raise ValueError("V3 nullspace row/parameter contract drifted")
        if self.replacement_model_selected:
            raise ValueError("V3 nullspace diagnostic cannot select a replacement model")
        if self.future_holdout_period != "2026Q3":
            raise ValueError("V3 nullspace future holdout drifted")
        if any(
            (
                self.future_holdout_loaded,
                self.future_holdout_evaluated,
                self.numeric_forward_forecast_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
            )
        ):
            raise ValueError("V3 nullspace diagnostic exceeded trust boundary")


def diagnose_v3_fit_report(path: str | Path) -> V3NullspaceReport:
    source = Path(path)
    try:
        raw: object = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"V3 fit report not found: {source}") from exc
    root = _mapping(raw, "fit report")
    if root.get("status") != _EXPECTED_STATUS:
        raise ValueError("V3 nullspace requires a completed V3 fit report")
    if root.get("2026q3_loaded") is not False or root.get("2026q3_evaluated") is not False:
        raise ValueError("V3 nullspace refuses a report that opened 2026Q3")
    result = _mapping(root.get("result"), "fit result")
    method_evidence_id = str(root.get("method_evidence_id", ""))
    if method_evidence_id != str(result.get("method_evidence_id", "")):
        raise ValueError("V3 nullspace method evidence binding diverged")
    periods, rows = _row_matrix(_items(result.get("rows"), "rows"))
    if len(periods) != 21:
        raise ValueError("V3 nullspace requires 21 clean rows")
    theta = _theta(result.get("parameters"))
    full = decompose_jacobian(build_jacobian(rows, theta))
    stored_rank = int(str(result.get("jacobian_rank", -1)))
    if stored_rank != full.rank:
        raise ValueError("V3 nullspace full Jacobian rank does not reproduce")
    prefit = _mapping(result.get("prefit_identification"), "prefit identification")
    linear_full = prefit.get("full_direction_design_rank") is True

    fold_outputs: list[FoldNullspaceDiagnostic] = []
    deficient: list[str] = []
    loocv = _items(result.get("loocv"), "loocv")
    if len(loocv) != len(periods):
        raise ValueError("V3 nullspace LOOCV count drifted")
    for raw_fold in loocv:
        fold = _mapping(raw_fold, "loocv fold")
        held = str(fold.get("held_out_period", ""))
        if held not in periods:
            raise ValueError("V3 nullspace LOOCV period is unknown")
        keep = np.asarray([period != held for period in periods], dtype=bool)
        fold_theta = _theta(fold.get("parameters_report_only"))
        decomposition = decompose_jacobian(build_jacobian(rows[keep], fold_theta))
        stored_fold_rank = int(str(fold.get("jacobian_rank", -1)))
        if stored_fold_rank != decomposition.rank:
            raise ValueError(f"V3 nullspace LOOCV rank does not reproduce: {held}")
        if decomposition.rank < len(PARAMETER_NAMES):
            deficient.append(held)
        dominant = decomposition.dominant_nullspace_direction_report_only[0].parameter_name
        fold_outputs.append(
            FoldNullspaceDiagnostic(
                held_out_period=held,
                jacobian_rank=decomposition.rank,
                normalized_condition_number_report_only=(
                    decomposition.normalized_condition_number_report_only
                ),
                smallest_to_largest_ratio_report_only=(
                    decomposition.smallest_to_largest_ratio_report_only
                ),
                dominant_parameter_report_only=dominant,
            )
        )

    source_fit_evidence_id = str(result.get("evidence_id", ""))
    stable = {
        "source_fit_evidence_id": source_fit_evidence_id,
        "method_evidence_id": method_evidence_id,
        "full_fit": asdict(full),
        "rank_deficient_loocv_periods": deficient,
        "folds": [asdict(item) for item in fold_outputs],
    }
    return V3NullspaceReport(
        evidence_id=_sha(stable),
        source_fit_evidence_id=source_fit_evidence_id,
        method_evidence_id=method_evidence_id,
        method_version=_EXPECTED_METHOD_VERSION,
        row_count=len(periods),
        parameter_count=len(PARAMETER_NAMES),
        linear_prefit_full_rank=linear_full,
        full_fit=full,
        rank_deficient_loocv_periods=tuple(deficient),
        loocv_rank_deficient_count=len(deficient),
        loocv_diagnostics_report_only=tuple(fold_outputs),
        nonlinear_rank_loss_after_link_fit=linear_full and full.rank < len(PARAMETER_NAMES),
    )


__all__ = ["FoldNullspaceDiagnostic", "V3NullspaceReport", "diagnose_v3_fit_report"]
