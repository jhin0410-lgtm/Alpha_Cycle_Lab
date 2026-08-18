"""Pure numerical diagnostics for SK hynix V3 nonlinear identification loss."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

PARAMETER_NAMES = (
    "dram_logit_intercept",
    "dram_asp_direction_effect",
    "dram_bit_volume_direction_effect",
    "nand_logit_intercept",
    "nand_asp_direction_effect",
    "nand_bit_volume_direction_effect",
    "other_logit_margin",
)


@dataclass(frozen=True)
class NullspaceLoading:
    parameter_name: str
    loading: float
    absolute_loading: float


@dataclass(frozen=True)
class ParameterDeletionDiagnostic:
    removed_parameter: str
    remaining_rank: int
    full_remaining_rank: bool
    normalized_condition_number_report_only: float | None


@dataclass(frozen=True)
class JacobianDecomposition:
    rank: int
    normalized_condition_number_report_only: float | None
    normalized_singular_values_report_only: tuple[float, ...]
    smallest_to_largest_ratio_report_only: float | None
    column_l2_norms_report_only: tuple[tuple[str, float], ...]
    dominant_nullspace_direction_report_only: tuple[NullspaceLoading, ...]
    deletion_diagnostics_report_only: tuple[ParameterDeletionDiagnostic, ...]


def sigmoid(value: np.ndarray) -> np.ndarray:
    clipped = np.asarray(np.clip(value, -60.0, 60.0), dtype=float)
    result = 1.0 / (1.0 + np.exp(-clipped))
    return np.asarray(result, dtype=float)


def normalized_condition(matrix: np.ndarray) -> float | None:
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        return None
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms == 0.0):
        return None
    value = float(np.linalg.cond(matrix / norms))
    return value if math.isfinite(value) else None


def build_jacobian(rows: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """Build the frozen seven-parameter V3 Jacobian from a compact 8-column row matrix."""

    if rows.ndim != 2 or rows.shape[1] != 8:
        raise ValueError("V3 nullspace rows must be n x 8")
    if theta.shape != (7,) or not np.all(np.isfinite(theta)):
        raise ValueError("V3 nullspace theta must contain seven finite values")
    revenue, dram, nand, other, da, db, na, nb = rows.T
    scale = float(np.mean(revenue))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("V3 nullspace revenue scale is invalid")
    dram = dram / scale
    nand = nand / scale
    other = other / scale
    md = sigmoid(theta[0] + theta[1] * da + theta[2] * db)
    mn = sigmoid(theta[3] + theta[4] * na + theta[5] * nb)
    mo = float(sigmoid(np.asarray([theta[6]], dtype=float))[0])
    dd = dram * md * (1.0 - md)
    dn = nand * mn * (1.0 - mn)
    do = other * mo * (1.0 - mo)
    return np.column_stack((dd, dd * da, dd * db, dn, dn * na, dn * nb, do))


def decompose_jacobian(jacobian: np.ndarray) -> JacobianDecomposition:
    if jacobian.ndim != 2 or jacobian.shape[1] != len(PARAMETER_NAMES):
        raise ValueError("V3 nullspace Jacobian must have seven columns")
    norms = np.linalg.norm(jacobian, axis=0)
    normalized = np.zeros_like(jacobian)
    nonzero = norms > 0.0
    normalized[:, nonzero] = jacobian[:, nonzero] / norms[nonzero]
    _u, singular, vh = np.linalg.svd(normalized, full_matrices=False)
    values = tuple(float(value) for value in singular)
    largest = values[0] if values else 0.0
    smallest = values[-1] if values else 0.0
    ratio = smallest / largest if largest > 0.0 else None
    vector = vh[-1] if len(vh) else np.zeros(len(PARAMETER_NAMES), dtype=float)
    loadings = tuple(
        sorted(
            (
                NullspaceLoading(name, float(vector[index]), abs(float(vector[index])))
                for index, name in enumerate(PARAMETER_NAMES)
            ),
            key=lambda item: item.absolute_loading,
            reverse=True,
        )
    )
    deletions: list[ParameterDeletionDiagnostic] = []
    for index, name in enumerate(PARAMETER_NAMES):
        reduced = np.delete(jacobian, index, axis=1)
        rank = int(np.linalg.matrix_rank(reduced))
        deletions.append(
            ParameterDeletionDiagnostic(
                removed_parameter=name,
                remaining_rank=rank,
                full_remaining_rank=rank == reduced.shape[1],
                normalized_condition_number_report_only=normalized_condition(reduced),
            )
        )
    return JacobianDecomposition(
        rank=int(np.linalg.matrix_rank(jacobian)),
        normalized_condition_number_report_only=normalized_condition(jacobian),
        normalized_singular_values_report_only=values,
        smallest_to_largest_ratio_report_only=ratio,
        column_l2_norms_report_only=tuple(
            (name, float(value)) for name, value in zip(PARAMETER_NAMES, norms, strict=True)
        ),
        dominant_nullspace_direction_report_only=loadings,
        deletion_diagnostics_report_only=tuple(deletions),
    )


__all__ = [
    "JacobianDecomposition",
    "NullspaceLoading",
    "PARAMETER_NAMES",
    "ParameterDeletionDiagnostic",
    "build_jacobian",
    "decompose_jacobian",
    "normalized_condition",
]
