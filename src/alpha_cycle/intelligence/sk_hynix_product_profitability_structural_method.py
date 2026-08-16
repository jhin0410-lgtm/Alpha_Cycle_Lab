"""Draft structural rank probe for latent SK hynix DRAM/NAND profitability.

This module is deliberately narrower than a profitability estimator.  It converts only
issuer-reported direction semantics (Increase / Flat / Decrease) into +1 / 0 / -1 for a
linear-design rank probe, while preserving the original magnitude text.  It never maps
phrases such as ``Mid-60% Increase`` to a numeric percentage and never estimates product
margins.

The rank design uses only quarters where three independently replayed source layers are
available for the same period: direct product revenue, company gross profit, and issuer
cycle-driver text.  Q1 2026 is reserved as holdout and cannot enter the training design.
A full-rank design is only evidence that the proposed low-dimensional parameterization is
algebraically identifiable under the direction-only transform; it is not evidence that the
model is economically valid or ready for estimation.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import cast

import numpy as np
import yaml

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
    QuarterlyProductCycleDriverObservation,
    SecProductCycleDriverSupportEvidence,
)
from alpha_cycle.intelligence.sec_product_cycle_driver_support_verifier import (
    load_sec_product_cycle_driver_support_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
    HistoricalProductRevenuePanelEvidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier import (
    load_historical_product_revenue_panel_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    OpenDartPeriodicProductRevenueCertification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
    QuarterlyCompanyProfitabilityEvidence,
    QuarterlyCompanyProfitabilityObservation,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability_verifier import (
    load_quarterly_company_profitability_evidence,
)

DEFAULT_STRUCTURAL_METHOD_PATH = Path(
    "config/skhynix_product_profitability_structural_method.v1.yaml"
)
DEFAULT_STRUCTURAL_RANK_PROBE_OUTPUT = Path(
    "data/private/research/skhynix-product-profitability-structural-rank-probe"
)
DEFAULT_STRUCTURAL_RANK_PROBE_POINTER = (
    DEFAULT_STRUCTURAL_RANK_PROBE_OUTPUT / "latest_structural_rank_probe.json"
)
_EXPECTED_PARAMETERS = (
    "dram_margin_intercept",
    "dram_asp_direction_sensitivity",
    "dram_bit_volume_direction_sensitivity",
    "nand_margin_intercept",
    "nand_asp_direction_sensitivity",
    "nand_bit_volume_direction_sensitivity",
    "other_margin_constant",
)
_EXPECTED_TERMS = (
    "dram_revenue",
    "dram_revenue_x_dram_asp_direction",
    "dram_revenue_x_dram_bit_volume_direction",
    "nand_revenue",
    "nand_revenue_x_nand_asp_direction",
    "nand_revenue_x_nand_bit_volume_direction",
    "other_revenue",
)
_ALLOWED_BLOCK_REASONS = frozenset(
    {
        "company_product_revenue_reconciliation_failed",
        "insufficient_aligned_training_rows",
        "design_not_full_column_rank",
        "direction_only_rank_probe_not_estimation_method",
    }
)


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha_payload(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Structural method {label} must be an array")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if not result:
        raise ValueError(f"Structural method {label} cannot be empty")
    return result


@dataclass(frozen=True)
class StructuralDirectionEncodingContract:
    encoding_id: str
    increase_code: float
    flat_code: float
    decrease_code: float
    preserves_magnitude_text: bool
    numeric_magnitude_assumed: bool
    rank_probe_only: bool
    estimation_input_ready: bool

    def __post_init__(self) -> None:
        if self.encoding_id != "issuer_direction_sign_v1":
            raise ValueError("Structural direction encoding id is unsupported")
        if (self.increase_code, self.flat_code, self.decrease_code) != (1.0, 0.0, -1.0):
            raise ValueError("Structural direction encoding must remain +1/0/-1")
        if (
            not self.preserves_magnitude_text
            or self.numeric_magnitude_assumed
            or not self.rank_probe_only
            or self.estimation_input_ready
        ):
            raise ValueError("Structural direction encoding widened beyond rank-probe use")


@dataclass(frozen=True)
class StructuralProfitabilityMethodContract:
    method_id: str
    method_version: str
    status: str
    ticker: str
    target_metric: str
    target_product_blocks: tuple[str, ...]
    nuisance_product_blocks: tuple[str, ...]
    temporal_alignment: str
    holdout_period: str
    driver_encoding: StructuralDirectionEncodingContract
    parameters: tuple[str, ...]
    equation_terms: tuple[str, ...]
    company_revenue_reconciliation_tolerance_krw: int
    minimum_training_rows_for_rank_probe: int
    fit_enabled: bool
    historical_validation_complete: bool
    holdout_validation_complete: bool
    method_version_frozen: bool
    product_profitability_source_fact: bool
    numeric_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool
    required_future_checks: tuple[str, ...]
    manifest_sha256: str

    def __post_init__(self) -> None:
        if self.method_id != "skhynix_aggregate_direction_rank_probe":
            raise ValueError("Structural profitability method id is unsupported")
        if self.method_version != "0.1-draft" or self.status != "draft_rank_probe_only":
            raise ValueError("Structural profitability method must remain draft rank-probe v0.1")
        if self.ticker != "000660":
            raise ValueError("Structural profitability method supports SK hynix only")
        if self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Structural profitability target metric is invalid")
        if self.target_product_blocks != ("dram_total", "nand_and_solutions"):
            raise ValueError("Structural profitability target blocks are invalid")
        if self.nuisance_product_blocks != ("other_products_services",):
            raise ValueError("Structural profitability nuisance block is invalid")
        if self.temporal_alignment != "contemporaneous_same_quarter":
            raise ValueError("Structural profitability temporal alignment is unsupported")
        if self.holdout_period != "2026Q1":
            raise ValueError("Structural profitability holdout must remain 2026Q1")
        if self.parameters != _EXPECTED_PARAMETERS or self.equation_terms != _EXPECTED_TERMS:
            raise ValueError("Structural profitability parameter/equation order drifted")
        if self.company_revenue_reconciliation_tolerance_krw != 1_000_000:
            raise ValueError("Structural profitability revenue tolerance must remain KRW 1 million")
        if self.minimum_training_rows_for_rank_probe != len(_EXPECTED_PARAMETERS):
            raise ValueError("Structural profitability rank probe requires seven rows minimum")
        forbidden = (
            self.fit_enabled,
            self.historical_validation_complete,
            self.holdout_validation_complete,
            self.method_version_frozen,
            self.product_profitability_source_fact,
            self.numeric_forecast_enabled,
            self.fair_value_estimate_enabled,
            self.target_price_enabled,
            self.decision_score_enabled,
        )
        if any(forbidden):
            raise ValueError("Draft structural profitability method opened a forbidden gate")
        if len(self.required_future_checks) < 6:
            raise ValueError("Structural profitability method must retain future validation checks")
        if not _valid_sha(self.manifest_sha256):
            raise ValueError("Structural profitability method manifest hash must be SHA-256")

    @property
    def parameter_count(self) -> int:
        return len(self.parameters)


@dataclass(frozen=True)
class DirectionSignEncoding:
    source_text: str
    direction: str
    code: float
    derived_numeric_source_fact: bool = False
    numeric_magnitude_assumed: bool = False
    estimation_input_ready: bool = False

    def __post_init__(self) -> None:
        if self.direction not in {"increase", "flat", "decrease"}:
            raise ValueError("Direction-sign encoding direction is invalid")
        expected = {"increase": 1.0, "flat": 0.0, "decrease": -1.0}[self.direction]
        if self.code != expected:
            raise ValueError("Direction-sign encoding code does not match direction")
        if (
            self.derived_numeric_source_fact
            or self.numeric_magnitude_assumed
            or self.estimation_input_ready
        ):
            raise ValueError("Direction-sign encoding exceeds rank-probe trust boundary")


def encode_direction_sign(source_text: str) -> DirectionSignEncoding:
    """Encode only direction semantics; never infer the magnitude hidden in issuer text."""

    text = " ".join(source_text.split())
    if text == "Flat":
        return DirectionSignEncoding(text, "flat", 0.0)
    if text.endswith(" Increase"):
        return DirectionSignEncoding(text, "increase", 1.0)
    if text.endswith(" Decrease"):
        return DirectionSignEncoding(text, "decrease", -1.0)
    raise ValueError(f"Unsupported issuer cycle-driver direction text: {source_text}")


def load_structural_profitability_method(
    path: str | Path = DEFAULT_STRUCTURAL_METHOD_PATH,
) -> StructuralProfitabilityMethodContract:
    method_path = Path(path)
    with method_path.open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Structural profitability method manifest schema is invalid")
    raw_method = payload.get("method")
    if not isinstance(raw_method, dict):
        raise ValueError("Structural profitability method manifest lacks method")
    method = cast(dict[object, object], raw_method)
    raw_encoding = method.get("driver_encoding")
    if not isinstance(raw_encoding, dict):
        raise ValueError("Structural profitability method lacks driver encoding")
    encoding = cast(dict[object, object], raw_encoding)
    manifest_hash = _sha_payload(payload)
    return StructuralProfitabilityMethodContract(
        method_id=str(method.get("method_id", "")).strip(),
        method_version=str(method.get("method_version", "")).strip(),
        status=str(method.get("status", "")).strip(),
        ticker=str(method.get("ticker", "")).strip().zfill(6),
        target_metric=str(method.get("target_metric", "")).strip(),
        target_product_blocks=_string_tuple(
            method.get("target_product_blocks"), "target_product_blocks"
        ),
        nuisance_product_blocks=_string_tuple(
            method.get("nuisance_product_blocks"), "nuisance_product_blocks"
        ),
        temporal_alignment=str(method.get("temporal_alignment", "")).strip(),
        holdout_period=str(method.get("holdout_period", "")).strip(),
        driver_encoding=StructuralDirectionEncodingContract(
            encoding_id=str(encoding.get("encoding_id", "")).strip(),
            increase_code=float(str(encoding.get("increase_code", "nan"))),
            flat_code=float(str(encoding.get("flat_code", "nan"))),
            decrease_code=float(str(encoding.get("decrease_code", "nan"))),
            preserves_magnitude_text=encoding.get("preserves_magnitude_text") is True,
            numeric_magnitude_assumed=encoding.get("numeric_magnitude_assumed") is True,
            rank_probe_only=encoding.get("rank_probe_only") is True,
            estimation_input_ready=encoding.get("estimation_input_ready") is True,
        ),
        parameters=_string_tuple(method.get("parameters"), "parameters"),
        equation_terms=_string_tuple(method.get("equation_terms"), "equation_terms"),
        company_revenue_reconciliation_tolerance_krw=int(
            str(method.get("company_revenue_reconciliation_tolerance_krw", -1))
        ),
        minimum_training_rows_for_rank_probe=int(
            str(method.get("minimum_training_rows_for_rank_probe", -1))
        ),
        fit_enabled=method.get("fit_enabled") is True,
        historical_validation_complete=method.get("historical_validation_complete") is True,
        holdout_validation_complete=method.get("holdout_validation_complete") is True,
        method_version_frozen=method.get("method_version_frozen") is True,
        product_profitability_source_fact=method.get("product_profitability_source_fact") is True,
        numeric_forecast_enabled=method.get("numeric_forecast_enabled") is True,
        fair_value_estimate_enabled=method.get("fair_value_estimate_enabled") is True,
        target_price_enabled=method.get("target_price_enabled") is True,
        decision_score_enabled=method.get("decision_score_enabled") is True,
        required_future_checks=_string_tuple(
            method.get("required_future_checks"), "required_future_checks"
        ),
        manifest_sha256=manifest_hash,
    )


@dataclass(frozen=True)
class StructuralRankProbeRow:
    period_id: str
    product_revenue_evidence_id: str
    product_revenue_krw_million: float
    company_revenue_krw_million: float
    company_gross_profit_krw_million: float
    revenue_reconciliation_delta_krw: int
    dram_revenue_krw_million: float
    nand_revenue_krw_million: float
    other_revenue_krw_million: float
    dram_asp: DirectionSignEncoding
    dram_bit_volume: DirectionSignEncoding
    nand_asp: DirectionSignEncoding
    nand_bit_volume: DirectionSignEncoding
    design_terms: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.period_id == "2026Q1":
            raise ValueError("Q1 2026 holdout cannot enter structural training rows")
        if not _valid_sha(self.product_revenue_evidence_id):
            raise ValueError("Structural rank row product evidence id must be SHA-256")
        if len(self.design_terms) != len(_EXPECTED_PARAMETERS):
            raise ValueError("Structural rank row must contain seven design terms")
        if self.product_revenue_krw_million <= 0 or self.company_revenue_krw_million <= 0:
            raise ValueError("Structural rank row revenue must be positive")
        if any(not math.isfinite(value) for value in self.design_terms):
            raise ValueError("Structural rank row design terms must be finite")


def _row_from_sources(
    method: StructuralProfitabilityMethodContract,
    product: OpenDartPeriodicProductRevenueCertification,
    company: QuarterlyCompanyProfitabilityObservation,
    cycle: QuarterlyProductCycleDriverObservation,
) -> StructuralRankProbeRow | None:
    period_id = cycle.period_id
    if period_id == method.holdout_period:
        return None
    product_total_krw = int(round(product.metrics.reported_company_revenue * 1_000_000.0))
    delta_krw = product_total_krw - company.revenue_krw
    if abs(delta_krw) > method.company_revenue_reconciliation_tolerance_krw:
        return None

    dram_asp = encode_direction_sign(cycle.dram_asp_usd_qoq_text)
    dram_bit = encode_direction_sign(cycle.dram_bit_sales_volume_qoq_text)
    nand_asp = encode_direction_sign(cycle.nand_asp_usd_qoq_text)
    nand_bit = encode_direction_sign(cycle.nand_bit_sales_volume_qoq_text)
    dram = float(product.metrics.dram_total)
    nand = float(product.metrics.nand_and_solutions)
    other = float(product.metrics.other_products_services)
    design_terms = (
        dram,
        dram * dram_asp.code,
        dram * dram_bit.code,
        nand,
        nand * nand_asp.code,
        nand * nand_bit.code,
        other,
    )
    return StructuralRankProbeRow(
        period_id=period_id,
        product_revenue_evidence_id=product.evidence_id,
        product_revenue_krw_million=float(product.metrics.reported_company_revenue),
        company_revenue_krw_million=company.revenue_krw / 1_000_000.0,
        company_gross_profit_krw_million=company.gross_profit_krw / 1_000_000.0,
        revenue_reconciliation_delta_krw=delta_krw,
        dram_revenue_krw_million=dram,
        nand_revenue_krw_million=nand,
        other_revenue_krw_million=other,
        dram_asp=dram_asp,
        dram_bit_volume=dram_bit,
        nand_asp=nand_asp,
        nand_bit_volume=nand_bit,
        design_terms=design_terms,
    )


def _normalized_condition_number(matrix: np.ndarray) -> float | None:
    if matrix.size == 0 or matrix.ndim != 2:
        return None
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms == 0.0):
        return None
    value = float(np.linalg.cond(matrix / norms))
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class StructuralRankProbeResult:
    evidence_id: str
    evaluation_date: date
    method_id: str
    method_version: str
    method_manifest_sha256: str
    historical_product_revenue_evidence_id: str
    company_profitability_evidence_id: str
    cycle_driver_evidence_id: str
    candidate_aligned_periods: tuple[str, ...]
    training_periods: tuple[str, ...]
    holdout_excluded_periods: tuple[str, ...]
    reconciliation_failed_periods: tuple[str, ...]
    rows: tuple[StructuralRankProbeRow, ...]
    row_count: int
    parameter_count: int
    design_rank: int
    full_column_rank: bool
    normalized_condition_number: float | None
    company_product_revenue_reconciliation_certified: bool
    rank_probe_ready: bool
    fit_attempt_allowed: bool
    holdout_evaluation_allowed: bool
    block_reason: str
    direction_encoding_numeric_source_fact: bool = False
    numeric_magnitude_assumed: bool = False
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.method_manifest_sha256,
            self.historical_product_revenue_evidence_id,
            self.company_profitability_evidence_id,
            self.cycle_driver_evidence_id,
        )
        if any(not _valid_sha(value) for value in hashes):
            raise ValueError("Structural rank-probe evidence hashes must be SHA-256")
        if self.row_count != len(self.rows) or self.training_periods != tuple(
            item.period_id for item in self.rows
        ):
            raise ValueError("Structural rank-probe row/period counts are inconsistent")
        if self.parameter_count != len(_EXPECTED_PARAMETERS):
            raise ValueError("Structural rank-probe parameter count drifted")
        if self.design_rank < 0 or self.design_rank > min(self.row_count, self.parameter_count):
            raise ValueError("Structural rank-probe matrix rank is invalid")
        if self.full_column_rank != (
            self.row_count >= self.parameter_count and self.design_rank == self.parameter_count
        ):
            raise ValueError("Structural rank-probe full-rank flag is inconsistent")
        expected_reconciliation = not self.reconciliation_failed_periods
        if self.company_product_revenue_reconciliation_certified != expected_reconciliation:
            raise ValueError("Structural rank-probe reconciliation flag is inconsistent")
        expected_ready = self.full_column_rank and expected_reconciliation
        if self.rank_probe_ready != expected_ready:
            raise ValueError("Structural rank-probe readiness flag is inconsistent")
        if self.block_reason not in _ALLOWED_BLOCK_REASONS:
            raise ValueError("Structural rank-probe block reason is invalid")
        if self.fit_attempt_allowed or self.holdout_evaluation_allowed:
            raise ValueError("Direction-only rank probe cannot open fit/holdout gates")
        if (
            self.direction_encoding_numeric_source_fact
            or self.numeric_magnitude_assumed
            or self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Structural rank probe exceeds its trust boundary")


def build_structural_rank_probe(
    method: StructuralProfitabilityMethodContract,
    historical: HistoricalProductRevenuePanelEvidence,
    company: QuarterlyCompanyProfitabilityEvidence,
    cycle: SecProductCycleDriverSupportEvidence,
    product_certifications: dict[str, OpenDartPeriodicProductRevenueCertification],
    *,
    evaluation_date: date,
) -> StructuralRankProbeResult:
    """Build a rank-only design from period-aligned, independently verified source layers."""

    evidence_tickers = (historical.ticker, company.ticker, cycle.ticker)
    if any(ticker != method.ticker for ticker in evidence_tickers):
        raise ValueError("Structural rank probe received evidence for another issuer")
    if historical.evaluation_date != evaluation_date or company.evaluation_date != evaluation_date:
        raise ValueError("Structural rank probe evidence evaluation date mismatch")
    if cycle.observed_date > evaluation_date:
        raise ValueError("Structural rank probe uses future cycle-driver evidence")
    if cycle.numeric_driver_values_available:
        raise ValueError(
            "Structural rank probe expects source-text cycle drivers, not numeric facts"
        )

    company_by_period = {item.period_id: item for item in company.observations}
    cycle_by_period = {item.period_id: item for item in cycle.observations}
    candidate = tuple(
        sorted(set(product_certifications) & set(company_by_period) & set(cycle_by_period))
    )
    holdout_excluded = tuple(period for period in candidate if period == method.holdout_period)
    training_candidates = tuple(period for period in candidate if period != method.holdout_period)

    rows: list[StructuralRankProbeRow] = []
    reconciliation_failed: list[str] = []
    for period_id in training_candidates:
        product = product_certifications[period_id]
        if product.period_end.year != int(period_id[:4]):
            raise ValueError("Structural rank probe product certification period/year mismatch")
        row = _row_from_sources(
            method,
            product,
            company_by_period[period_id],
            cycle_by_period[period_id],
        )
        if row is None:
            reconciliation_failed.append(period_id)
        else:
            rows.append(row)

    matrix = np.asarray([item.design_terms for item in rows], dtype=float)
    if not rows:
        matrix = np.empty((0, method.parameter_count), dtype=float)
    design_rank = int(np.linalg.matrix_rank(matrix)) if rows else 0
    full_rank = len(rows) >= method.parameter_count and design_rank == method.parameter_count
    condition_number = _normalized_condition_number(matrix)
    reconciliation_certified = not reconciliation_failed
    rank_probe_ready = full_rank and reconciliation_certified

    if reconciliation_failed:
        block_reason = "company_product_revenue_reconciliation_failed"
    elif len(rows) < method.minimum_training_rows_for_rank_probe:
        block_reason = "insufficient_aligned_training_rows"
    elif not full_rank:
        block_reason = "design_not_full_column_rank"
    else:
        block_reason = "direction_only_rank_probe_not_estimation_method"

    stable_payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "method_id": method.method_id,
        "method_version": method.method_version,
        "method_manifest_sha256": method.manifest_sha256,
        "historical_product_revenue_evidence_id": historical.evidence_id,
        "company_profitability_evidence_id": company.evidence_id,
        "cycle_driver_evidence_id": cycle.evidence_id,
        "candidate_aligned_periods": candidate,
        "training_periods": tuple(item.period_id for item in rows),
        "holdout_excluded_periods": holdout_excluded,
        "reconciliation_failed_periods": tuple(reconciliation_failed),
        "rows": [asdict(item) for item in rows],
        "parameter_count": method.parameter_count,
        "design_rank": design_rank,
        "full_column_rank": full_rank,
        "normalized_condition_number": condition_number,
        "rank_probe_ready": rank_probe_ready,
        "fit_attempt_allowed": False,
        "holdout_evaluation_allowed": False,
    }
    return StructuralRankProbeResult(
        evidence_id=_sha_payload(stable_payload),
        evaluation_date=evaluation_date,
        method_id=method.method_id,
        method_version=method.method_version,
        method_manifest_sha256=method.manifest_sha256,
        historical_product_revenue_evidence_id=historical.evidence_id,
        company_profitability_evidence_id=company.evidence_id,
        cycle_driver_evidence_id=cycle.evidence_id,
        candidate_aligned_periods=candidate,
        training_periods=tuple(item.period_id for item in rows),
        holdout_excluded_periods=holdout_excluded,
        reconciliation_failed_periods=tuple(reconciliation_failed),
        rows=tuple(rows),
        row_count=len(rows),
        parameter_count=method.parameter_count,
        design_rank=design_rank,
        full_column_rank=full_rank,
        normalized_condition_number=condition_number,
        company_product_revenue_reconciliation_certified=reconciliation_certified,
        rank_probe_ready=rank_probe_ready,
        fit_attempt_allowed=False,
        holdout_evaluation_allowed=False,
        block_reason=block_reason,
    )


def load_product_certifications_for_historical_panel(
    historical: HistoricalProductRevenuePanelEvidence,
    *,
    evaluation_date: date,
) -> dict[str, OpenDartPeriodicProductRevenueCertification]:
    certifications: dict[str, OpenDartPeriodicProductRevenueCertification] = {}
    for entry in historical.entries:
        if entry.status != "certified":
            continue
        if entry.pointer_path is None:
            raise ValueError("Certified historical product-revenue entry lacks pointer path")
        certification = load_periodic_product_revenue_certification(
            Path(entry.pointer_path),
            evaluation_date=evaluation_date,
        )
        if certification.evidence_id != entry.certification_evidence_id:
            raise ValueError("Historical product-revenue entry evidence binding diverged")
        certifications[entry.period_id] = certification
    if tuple(sorted(certifications)) != tuple(sorted(historical.successful_periods)):
        raise ValueError("Historical product-revenue certifications do not reproduce panel periods")
    return certifications


def load_structural_rank_probe_from_pointers(
    *,
    evaluation_date: date,
    method_path: str | Path = DEFAULT_STRUCTURAL_METHOD_PATH,
    historical_product_revenue_pointer: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
    company_profitability_pointer: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
    cycle_driver_pointer: str | Path = DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
) -> StructuralRankProbeResult:
    method = load_structural_profitability_method(method_path)
    historical = load_historical_product_revenue_panel_evidence(
        historical_product_revenue_pointer,
        evaluation_date=evaluation_date,
    )
    company = load_quarterly_company_profitability_evidence(
        company_profitability_pointer,
        evaluation_date=evaluation_date,
    )
    cycle = load_sec_product_cycle_driver_support_evidence(
        cycle_driver_pointer,
        evaluation_date=evaluation_date,
    )
    certifications = load_product_certifications_for_historical_panel(
        historical,
        evaluation_date=evaluation_date,
    )
    return build_structural_rank_probe(
        method,
        historical,
        company,
        cycle,
        certifications,
        evaluation_date=evaluation_date,
    )


__all__ = [
    "DEFAULT_STRUCTURAL_METHOD_PATH",
    "DEFAULT_STRUCTURAL_RANK_PROBE_OUTPUT",
    "DEFAULT_STRUCTURAL_RANK_PROBE_POINTER",
    "DirectionSignEncoding",
    "StructuralDirectionEncodingContract",
    "StructuralProfitabilityMethodContract",
    "StructuralRankProbeResult",
    "StructuralRankProbeRow",
    "build_structural_rank_probe",
    "encode_direction_sign",
    "load_product_certifications_for_historical_panel",
    "load_structural_profitability_method",
    "load_structural_rank_probe_from_pointers",
]
