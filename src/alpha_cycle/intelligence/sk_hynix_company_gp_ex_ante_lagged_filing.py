"""Certify lagged immutable filing facts as target-blind PIT features for SK hynix.

This layer does not change the trust flags of the original calibration objects. Instead it
builds a derived point-in-time feature bundle only when the exact filing receipt, preserved
company JSON bytes, preserved product ZIP bytes, accounting identities, product/company
reconciliation, and the frozen forecast-origin timing all agree.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    ExAnteFeatureFrontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    ExAntePITAuditResult,
    PointInTimeFeatureBundle,
    PointInTimeFeatureObservation,
    audit_point_in_time_feature_bundle,
    load_point_in_time_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    FrozenCompanyGPExAnteProtocol,
)
from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    load_failure_diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier import (
    load_historical_product_revenue_panel_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
    QuarterlyCompanyProfitabilityObservation,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability_verifier import (
    load_quarterly_company_profitability_evidence,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_acquisition import (
    DEFAULT_SECOND_WAVE_COMPANY_OUTPUT,
    DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_closeout import (
    SecondWaveCloseout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    load_product_certifications_for_historical_panel,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_closeout import (
    DEFAULT_THIRD_WAVE_COMPANY_OUTPUT,
    DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT,
    ThirdWaveCloseout,
)

DEFAULT_LAGGED_FILING_CERTIFICATION = Path(
    "config/skhynix_company_gp_ex_ante_lagged_filing_certification.v1.yaml"
)
DEFAULT_LAGGED_FILING_PIT_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-pit"
)
DEFAULT_LAGGED_FILING_BUNDLE = (
    DEFAULT_LAGGED_FILING_PIT_OUTPUT / "latest_lagged_filing_feature_bundle.json"
)
DEFAULT_LAGGED_FILING_REPORT = (
    DEFAULT_LAGGED_FILING_PIT_OUTPUT / "latest_lagged_filing_certification.json"
)
_KOREA_TZ = ZoneInfo("Asia/Seoul")
_EXPECTED_SOURCE_PERIODS = (
    "2017Q1",
    "2017Q2",
    "2018Q1",
    "2018Q2",
    "2019Q1",
    "2019Q2",
    "2020Q1",
    "2020Q2",
    "2023Q1",
    "2023Q2",
    "2024Q1",
    "2024Q2",
    "2025Q1",
    "2025Q2",
)
_EXPECTED_TARGET_PERIODS = (
    "2017Q2",
    "2017Q3",
    "2018Q2",
    "2018Q3",
    "2019Q2",
    "2019Q3",
    "2020Q2",
    "2020Q3",
    "2023Q2",
    "2023Q3",
    "2024Q2",
    "2024Q3",
    "2025Q2",
    "2025Q3",
)
_FEATURE_IDS = (
    "lagged_company_revenue",
    "lagged_company_gross_profit",
    "lagged_company_gross_margin",
    "lagged_nand_revenue_share",
    "lagged_other_revenue_share",
)


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Lagged filing {label} must be an object")
    return cast(dict[object, object], value)


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _receipt_date(rcept_no: str) -> date:
    if len(rcept_no) != 14 or not rcept_no.isdigit():
        raise ValueError("Lagged filing receipt number must be 14 digits")
    return date(int(rcept_no[:4]), int(rcept_no[4:6]), int(rcept_no[6:8]))


def _source_available_at(receipt_date: date) -> datetime:
    return datetime.combine(receipt_date, time(23, 59, 59), tzinfo=_KOREA_TZ)


def _observation_payload(observation: PointInTimeFeatureObservation) -> dict[str, object]:
    payload = asdict(observation)
    payload["source_available_at"] = observation.source_available_at.isoformat()
    payload["captured_at"] = (
        observation.captured_at.isoformat() if observation.captured_at is not None else None
    )
    return payload


def _bundle_stable_payload(
    created_at: datetime,
    observations: tuple[PointInTimeFeatureObservation, ...],
) -> dict[str, object]:
    return {
        "created_at": created_at.isoformat(),
        "observations": [_observation_payload(item) for item in observations],
        "target_values_included": False,
    }


def build_locked_pit_feature_bundle(
    *,
    created_at: datetime,
    observations: tuple[PointInTimeFeatureObservation, ...],
) -> PointInTimeFeatureBundle:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("Lagged filing bundle created_at must be timezone-aware")
    stable = _bundle_stable_payload(created_at, observations)
    return PointInTimeFeatureBundle(
        evidence_id=_sha(stable),
        created_at=created_at,
        observations=observations,
        target_values_included=False,
    )


def persist_locked_pit_feature_bundle(
    bundle: PointInTimeFeatureBundle,
    path: str | Path = DEFAULT_LAGGED_FILING_BUNDLE,
) -> Path:
    stable = _bundle_stable_payload(bundle.created_at, bundle.observations)
    if _sha(stable) != bundle.evidence_id:
        raise ValueError("Lagged filing bundle evidence hash drifted before persistence")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "skhynix_ex_ante_pit_feature_bundle_locked",
        "bundle": {
            "evidence_id": bundle.evidence_id,
            **stable,
        },
    }
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(output)
    reloaded = load_point_in_time_feature_bundle(output)
    if reloaded.evidence_id != bundle.evidence_id:
        raise ValueError("Lagged filing persisted bundle failed exact replay")
    return output


@dataclass(frozen=True)
class LaggedFilingCertificationContract:
    evidence_id: str
    certification_id: str
    certification_version: str
    status: str
    ticker: str
    source_to_target_mapping: tuple[tuple[str, str], ...]
    expected_source_periods: tuple[str, ...]
    expected_target_periods: tuple[str, ...]
    expected_target_row_count: int
    expected_features_per_target_row: int
    expected_feature_observation_count: int
    feature_ids: tuple[str, ...]
    require_company_and_product_same_rcept_no: bool
    require_source_available_by_target_forecast_origin: bool
    q1_target_rows_supported: bool
    target_join_allowed: bool
    estimator_fit_allowed: bool
    first_pit_backtest_run: bool
    q3_target_read: bool
    q3_source_outcome_loaded: bool

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("Lagged filing certification evidence id must be SHA-256")
        if self.certification_id != "skhynix_company_gp_ex_ante_lagged_filing_pit":
            raise ValueError("Lagged filing certification id drifted")
        if (
            self.certification_version != "1.0-frozen-pre-certification"
            or self.status != "frozen_pre_certification"
        ):
            raise ValueError("Lagged filing certification is not frozen pre-certification")
        if self.ticker != "000660":
            raise ValueError("Lagged filing certification ticker drifted")
        if self.expected_source_periods != _EXPECTED_SOURCE_PERIODS:
            raise ValueError("Lagged filing source periods drifted")
        if self.expected_target_periods != _EXPECTED_TARGET_PERIODS:
            raise ValueError("Lagged filing target periods drifted")
        if tuple(target for _source, target in self.source_to_target_mapping) != (
            self.expected_target_periods
        ):
            raise ValueError("Lagged filing source-target mapping order drifted")
        if tuple(source for source, _target in self.source_to_target_mapping) != (
            self.expected_source_periods
        ):
            raise ValueError("Lagged filing source-target source order drifted")
        if (
            self.expected_target_row_count != 14
            or self.expected_features_per_target_row != 5
            or self.expected_feature_observation_count != 70
        ):
            raise ValueError("Lagged filing expected dimensions drifted")
        if self.feature_ids != _FEATURE_IDS:
            raise ValueError("Lagged filing feature set drifted")
        if not (
            self.require_company_and_product_same_rcept_no
            and self.require_source_available_by_target_forecast_origin
        ):
            raise ValueError("Lagged filing required source gates drifted")
        if self.q1_target_rows_supported:
            raise ValueError("Lagged filing certification cannot synthesize Q1 target rows")
        if any(
            (
                self.target_join_allowed,
                self.estimator_fit_allowed,
                self.first_pit_backtest_run,
                self.q3_target_read,
                self.q3_source_outcome_loaded,
            )
        ):
            raise ValueError("Lagged filing certification opened prohibited scope")

    @property
    def target_by_source(self) -> dict[str, str]:
        return dict(self.source_to_target_mapping)


def load_lagged_filing_certification_contract(
    path: str | Path = DEFAULT_LAGGED_FILING_CERTIFICATION,
) -> LaggedFilingCertificationContract:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Lagged filing certification schema is invalid")
    body = _mapping(root.get("certification"), "body")
    raw_mapping = _mapping(body.get("source_to_target_mapping"), "source_to_target_mapping")
    source_periods_raw = body.get("expected_source_periods")
    target_periods_raw = body.get("expected_target_periods")
    feature_ids_raw = body.get("feature_ids")
    if not isinstance(source_periods_raw, list) or not isinstance(target_periods_raw, list):
        raise ValueError("Lagged filing period lists are invalid")
    if not isinstance(feature_ids_raw, list):
        raise ValueError("Lagged filing feature_ids must be an array")
    source_periods = tuple(str(item) for item in source_periods_raw)
    source_to_target = tuple((source, str(raw_mapping.get(source, ""))) for source in source_periods)
    source_policy = _mapping(body.get("source_policy"), "source_policy")
    exclusions = _mapping(body.get("exclusions"), "exclusions")
    trust = _mapping(body.get("trust_boundary"), "trust_boundary")
    stable = {"schema_version": root["schema_version"], "certification": body}
    return LaggedFilingCertificationContract(
        evidence_id=_sha(stable),
        certification_id=str(body.get("certification_id", "")),
        certification_version=str(body.get("certification_version", "")),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        source_to_target_mapping=source_to_target,
        expected_source_periods=source_periods,
        expected_target_periods=tuple(str(item) for item in target_periods_raw),
        expected_target_row_count=int(
            str(body.get("expected_target_row_count_if_complete", -1))
        ),
        expected_features_per_target_row=int(
            str(body.get("expected_features_per_target_row", -1))
        ),
        expected_feature_observation_count=int(
            str(body.get("expected_feature_observation_count_if_complete", -1))
        ),
        feature_ids=tuple(str(item) for item in feature_ids_raw),
        require_company_and_product_same_rcept_no=(
            source_policy.get("require_company_and_product_same_rcept_no") is True
        ),
        require_source_available_by_target_forecast_origin=(
            source_policy.get("require_source_available_by_target_forecast_origin") is True
        ),
        q1_target_rows_supported=exclusions.get("q1_target_rows_supported") is True,
        target_join_allowed=trust.get("target_join_allowed") is True,
        estimator_fit_allowed=trust.get("estimator_fit_allowed") is True,
        first_pit_backtest_run=trust.get("first_pit_backtest_run") is True,
        q3_target_read=trust.get("2026q3_target_read") is True,
        q3_source_outcome_loaded=trust.get("2026q3_source_outcome_loaded") is True,
    )


@dataclass(frozen=True)
class LaggedFilingSourceRecord:
    source_period: str
    target_period: str
    rcept_no: str
    receipt_date: date
    company_revenue_krw: int
    company_gross_profit_krw: int
    company_raw_payload_sha256: str
    company_raw_path: str
    product_evidence_id: str
    product_archive_sha256: str
    product_archive_path: str
    nand_revenue_krw_million: float
    other_revenue_krw_million: float
    product_total_revenue_krw_million: float

    def __post_init__(self) -> None:
        if self.receipt_date != _receipt_date(self.rcept_no):
            raise ValueError("Lagged filing receipt/date identity drifted")
        if self.company_revenue_krw <= 0:
            raise ValueError("Lagged filing company revenue must be positive")
        if not math.isfinite(float(self.company_gross_profit_krw)):
            raise ValueError("Lagged filing company gross profit must be finite")
        for value in (
            self.company_raw_payload_sha256,
            self.product_evidence_id,
            self.product_archive_sha256,
        ):
            if not _valid_sha(value):
                raise ValueError("Lagged filing source hashes must be SHA-256")
        if min(
            self.nand_revenue_krw_million,
            self.other_revenue_krw_million,
            self.product_total_revenue_krw_million,
        ) < 0.0:
            raise ValueError("Lagged filing product revenue cannot be negative")
        if self.product_total_revenue_krw_million <= 0.0:
            raise ValueError("Lagged filing product total must be positive")


@dataclass(frozen=True)
class LaggedFilingPeriodCertification:
    source_period: str
    target_period: str
    rcept_no: str
    source_available_at: datetime
    company_raw_bytes_sha256: str
    product_archive_sha256: str
    feature_ids: tuple[str, ...]
    observations: tuple[PointInTimeFeatureObservation, ...]
    certified: bool = True
    target_read: bool = False

    def __post_init__(self) -> None:
        if not self.certified or self.target_read:
            raise ValueError("Lagged filing period certification exceeded source-only boundary")
        if self.feature_ids != _FEATURE_IDS or len(self.observations) != 5:
            raise ValueError("Lagged filing period must certify exactly five features")
        if any(item.period_id != self.target_period for item in self.observations):
            raise ValueError("Lagged filing observations target-period binding drifted")


@dataclass(frozen=True)
class LaggedFilingCertificationResult:
    contract_evidence_id: str
    period_certifications: tuple[LaggedFilingPeriodCertification, ...]
    certified_target_periods: tuple[str, ...]
    certified_target_row_count: int
    feature_observation_count: int
    bundle_evidence_id: str
    pit_audit: ExAntePITAuditResult
    completion_gate_passed: bool
    q1_target_rows_unavailable: bool = True
    target_values_included: bool = False
    target_join_allowed: bool = False
    estimator_fit_allowed: bool = False
    first_pit_backtest_run: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.contract_evidence_id) or not _valid_sha(
            self.bundle_evidence_id
        ):
            raise ValueError("Lagged filing result evidence ids must be SHA-256")
        if self.certified_target_row_count != len(self.period_certifications):
            raise ValueError("Lagged filing result row count drifted")
        if self.feature_observation_count != 5 * self.certified_target_row_count:
            raise ValueError("Lagged filing result feature count drifted")
        expected_gate = (
            self.certified_target_periods == _EXPECTED_TARGET_PERIODS
            and self.certified_target_row_count == 14
            and self.feature_observation_count == 70
            and self.pit_audit.eligible_observation_count == 70
            and self.pit_audit.rejected_observation_count == 0
        )
        if self.completion_gate_passed != expected_gate:
            raise ValueError("Lagged filing completion gate flag is inconsistent")
        if not self.q1_target_rows_unavailable or any(
            (
                self.target_values_included,
                self.target_join_allowed,
                self.estimator_fit_allowed,
                self.first_pit_backtest_run,
                self.q3_target_read,
                self.q3_source_outcome_loaded,
            )
        ):
            raise ValueError("Lagged filing result exceeded PIT source-certification boundary")


def _company_file_identity(
    record: LaggedFilingSourceRecord,
) -> tuple[str, str]:
    path = Path(record.company_raw_path)
    raw_bytes = path.read_bytes()
    raw_bytes_sha = _sha_bytes(raw_bytes)
    raw_object: object = json.loads(raw_bytes.decode("utf-8"))
    if _sha(raw_object) != record.company_raw_payload_sha256:
        raise ValueError(
            f"Lagged filing company raw JSON canonical hash mismatch: {record.source_period}"
        )
    evidence_id = _sha(
        {
            "source_period": record.source_period,
            "rcept_no": record.rcept_no,
            "receipt_date": record.receipt_date.isoformat(),
            "raw_bytes_sha256": raw_bytes_sha,
            "raw_payload_sha256": record.company_raw_payload_sha256,
            "company_revenue_krw": record.company_revenue_krw,
            "company_gross_profit_krw": record.company_gross_profit_krw,
        }
    )
    return raw_bytes_sha, evidence_id


def certify_lagged_filing_source_record(
    contract: LaggedFilingCertificationContract,
    protocol: FrozenCompanyGPExAnteProtocol,
    record: LaggedFilingSourceRecord,
) -> LaggedFilingPeriodCertification:
    expected_target = contract.target_by_source.get(record.source_period)
    if expected_target != record.target_period:
        raise ValueError("Lagged filing source-target mapping diverged from frozen contract")
    source_available_at = _source_available_at(record.receipt_date)
    if source_available_at > protocol.origin_for(record.target_period):
        raise ValueError(
            f"Lagged filing source was unavailable by forecast origin: {record.source_period}"
        )
    company_bytes_sha, company_evidence_id = _company_file_identity(record)
    product_bytes = Path(record.product_archive_path).read_bytes()
    if _sha_bytes(product_bytes) != record.product_archive_sha256:
        raise ValueError(
            f"Lagged filing product archive SHA-256 mismatch: {record.source_period}"
        )
    company_revenue_million = record.company_revenue_krw / 1_000_000.0
    if abs(company_revenue_million - record.product_total_revenue_krw_million) > 1.0:
        raise ValueError(
            f"Lagged filing product/company revenue reconciliation failed: {record.source_period}"
        )
    company_gp_million = record.company_gross_profit_krw / 1_000_000.0
    gross_margin = record.company_gross_profit_krw / record.company_revenue_krw
    nand_share = record.nand_revenue_krw_million / record.product_total_revenue_krw_million
    other_share = record.other_revenue_krw_million / record.product_total_revenue_krw_million
    if not all(math.isfinite(item) for item in (gross_margin, nand_share, other_share)):
        raise ValueError("Lagged filing deterministic transforms must be finite")
    if not 0.0 <= nand_share <= 1.0 or not 0.0 <= other_share <= 1.0:
        raise ValueError("Lagged filing product revenue shares must be inside [0,1]")
    version = f"opendart_rcept_no:{record.rcept_no};source_period:{record.source_period}"
    company_direct = (
        ("lagged_company_revenue", company_revenue_million),
        ("lagged_company_gross_profit", company_gp_million),
    )
    observations: list[PointInTimeFeatureObservation] = []
    for feature_id, value in company_direct:
        observations.append(
            PointInTimeFeatureObservation(
                period_id=record.target_period,
                feature_id=feature_id,
                value=value,
                provenance_class="timestamped_immutable_filing",
                source_available_at=source_available_at,
                source_bytes_sha256=company_bytes_sha,
                source_evidence_id=company_evidence_id,
                source_version_identity=version,
                direct_source_fact=True,
                deterministic_transform=False,
            )
        )
    observations.append(
        PointInTimeFeatureObservation(
            period_id=record.target_period,
            feature_id="lagged_company_gross_margin",
            value=gross_margin,
            provenance_class="timestamped_immutable_filing",
            source_available_at=source_available_at,
            source_bytes_sha256=company_bytes_sha,
            source_evidence_id=company_evidence_id,
            source_version_identity=version,
            direct_source_fact=False,
            deterministic_transform=True,
        )
    )
    for feature_id, value in (
        ("lagged_nand_revenue_share", nand_share),
        ("lagged_other_revenue_share", other_share),
    ):
        observations.append(
            PointInTimeFeatureObservation(
                period_id=record.target_period,
                feature_id=feature_id,
                value=value,
                provenance_class="timestamped_immutable_filing",
                source_available_at=source_available_at,
                source_bytes_sha256=record.product_archive_sha256,
                source_evidence_id=record.product_evidence_id,
                source_version_identity=version,
                direct_source_fact=False,
                deterministic_transform=True,
            )
        )
    ordered = tuple(observations)
    if tuple(item.feature_id for item in ordered) != _FEATURE_IDS:
        raise ValueError("Lagged filing observation feature order drifted")
    return LaggedFilingPeriodCertification(
        source_period=record.source_period,
        target_period=record.target_period,
        rcept_no=record.rcept_no,
        source_available_at=source_available_at,
        company_raw_bytes_sha256=company_bytes_sha,
        product_archive_sha256=record.product_archive_sha256,
        feature_ids=_FEATURE_IDS,
        observations=ordered,
    )


def _company_probe_raw_paths(root: Path) -> dict[str, Path]:
    payload = _json_object(root / "latest_company_probe.json", "Lagged filing company probe")
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("Lagged filing company probe results must be an array")
    result: dict[str, Path] = {}
    for raw_item in raw_results:
        if not isinstance(raw_item, dict):
            continue
        item = {str(key): value for key, value in cast(dict[object, object], raw_item).items()}
        period_id = str(item.get("period_id", ""))
        path_raw = item.get("raw_payload_path")
        if period_id and path_raw:
            result[period_id] = Path(str(path_raw))
    return result


def _latest_failure_diagnostic(period_root: Path) -> Path:
    failed_root = period_root / "failed"
    if not failed_root.is_dir():
        raise ValueError(f"Lagged filing product failure root missing: {period_root}")
    candidates = sorted(
        (item / "diagnostic.json" for item in failed_root.iterdir() if item.is_dir()),
        key=lambda item: item.parent.name,
        reverse=True,
    )
    found = next((item for item in candidates if item.is_file()), None)
    if found is None:
        raise ValueError(f"Lagged filing product diagnostic missing: {period_root}")
    return found


def _record_from_legacy_closeout_period(
    *,
    source_period: str,
    target_period: str,
    closeout: SecondWaveCloseout,
    product_root: Path,
    company_raw_paths: dict[str, Path],
    evaluation_date: date,
) -> LaggedFilingSourceRecord:
    period = next((item for item in closeout.periods if item.period_id == source_period), None)
    if period is None or not period.source_layer_complete or period.company_observation is None:
        raise ValueError(f"Lagged filing legacy source layer incomplete: {source_period}")
    company = period.company_observation
    raw_path = company_raw_paths.get(source_period)
    if raw_path is None:
        raise ValueError(f"Lagged filing legacy company raw path missing: {source_period}")
    direct_pointer = product_root / source_period / "latest_certification.json"
    if direct_pointer.is_file():
        direct_product = load_periodic_product_revenue_certification(
            direct_pointer,
            evaluation_date=evaluation_date,
        )
        pointer = _json_object(direct_pointer, "Lagged filing direct product pointer")
        archive_path = Path(str(pointer.get("archive_path", "")))
        archive_sha = direct_product.archive_sha256
        product_evidence_id = direct_product.evidence_id
        product_rcept_no = direct_product.rcept_no
        nand = float(direct_product.metrics.nand_and_solutions)
        other = float(direct_product.metrics.other_products_services)
        total = float(direct_product.metrics.reported_company_revenue)
    else:
        if period.product_recovery is None or period.product_recovery.observation is None:
            raise ValueError(f"Lagged filing legacy product recovery missing: {source_period}")
        recovered_product = period.product_recovery.observation
        diagnostic = load_failure_diagnostic(
            source_period,
            _latest_failure_diagnostic(product_root / source_period),
        )
        archive_path = Path(diagnostic.archive_path)
        archive_sha = recovered_product.source_archive_sha256
        product_evidence_id = recovered_product.evidence_id
        product_rcept_no = recovered_product.rcept_no
        nand = float(recovered_product.nand_revenue_million_krw)
        other = float(recovered_product.other_revenue_million_krw)
        total = float(recovered_product.total_revenue_million_krw)
    if company.rcept_no != product_rcept_no:
        raise ValueError(f"Lagged filing company/product receipt mismatch: {source_period}")
    if company.available_date != _receipt_date(company.rcept_no):
        raise ValueError(f"Lagged filing company availability/receipt mismatch: {source_period}")
    return LaggedFilingSourceRecord(
        source_period=source_period,
        target_period=target_period,
        rcept_no=company.rcept_no,
        receipt_date=company.available_date,
        company_revenue_krw=company.revenue_krw,
        company_gross_profit_krw=company.gross_profit_krw,
        company_raw_payload_sha256=company.raw_payload_sha256,
        company_raw_path=str(raw_path),
        product_evidence_id=product_evidence_id,
        product_archive_sha256=archive_sha,
        product_archive_path=str(archive_path),
        nand_revenue_krw_million=nand,
        other_revenue_krw_million=other,
        product_total_revenue_krw_million=total,
    )


def _modern_company_raw_directory(pointer: Path) -> Path:
    payload = _json_object(pointer, "Lagged filing modern company pointer")
    raw_dir = Path(str(payload.get("raw_directory", "")))
    if not raw_dir.is_dir():
        raise ValueError("Lagged filing modern company raw directory is missing")
    return raw_dir


def _modern_product_archive(pointer_path: str) -> Path:
    payload = _json_object(Path(pointer_path), "Lagged filing modern product pointer")
    archive = Path(str(payload.get("archive_path", "")))
    if not archive.is_file():
        raise ValueError("Lagged filing modern product archive is missing")
    return archive


def build_lagged_filing_source_records(
    contract: LaggedFilingCertificationContract,
    *,
    third_wave_closeout: ThirdWaveCloseout,
    second_wave_closeout: SecondWaveCloseout,
    evaluation_date: date,
    third_product_output: str | Path = DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT,
    third_company_output: str | Path = DEFAULT_THIRD_WAVE_COMPANY_OUTPUT,
    second_product_output: str | Path = DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT,
    second_company_output: str | Path = DEFAULT_SECOND_WAVE_COMPANY_OUTPUT,
    modern_product_pointer: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
    modern_company_pointer: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
) -> tuple[LaggedFilingSourceRecord, ...]:
    if not third_wave_closeout.all_six_source_layers_complete:
        raise ValueError("Lagged filing requires complete 2017-2018 third-wave source layers")
    if not second_wave_closeout.all_six_source_layers_complete:
        raise ValueError("Lagged filing requires complete 2019-2020 second-wave source layers")
    third_product_root = Path(third_product_output)
    second_product_root = Path(second_product_output)
    third_company_paths = _company_probe_raw_paths(Path(third_company_output))
    second_company_paths = _company_probe_raw_paths(Path(second_company_output))
    third_source = third_wave_closeout.source

    records: list[LaggedFilingSourceRecord] = []
    for source_period in _EXPECTED_SOURCE_PERIODS[:8]:
        target_period = contract.target_by_source[source_period]
        if source_period.startswith(("2017", "2018")):
            records.append(
                _record_from_legacy_closeout_period(
                    source_period=source_period,
                    target_period=target_period,
                    closeout=third_source,
                    product_root=third_product_root,
                    company_raw_paths=third_company_paths,
                    evaluation_date=evaluation_date,
                )
            )
        else:
            records.append(
                _record_from_legacy_closeout_period(
                    source_period=source_period,
                    target_period=target_period,
                    closeout=second_wave_closeout,
                    product_root=second_product_root,
                    company_raw_paths=second_company_paths,
                    evaluation_date=evaluation_date,
                )
            )

    historical = load_historical_product_revenue_panel_evidence(
        modern_product_pointer,
        evaluation_date=evaluation_date,
    )
    certifications = load_product_certifications_for_historical_panel(
        historical,
        evaluation_date=evaluation_date,
    )
    company_evidence = load_quarterly_company_profitability_evidence(
        modern_company_pointer,
        evaluation_date=evaluation_date,
    )
    company_by_period: dict[str, QuarterlyCompanyProfitabilityObservation] = {
        item.period_id: item for item in company_evidence.observations
    }
    panel_entry_by_period = {item.period_id: item for item in historical.entries}
    raw_directory = _modern_company_raw_directory(Path(modern_company_pointer))
    for source_period in _EXPECTED_SOURCE_PERIODS[8:]:
        target_period = contract.target_by_source[source_period]
        company = company_by_period.get(source_period)
        product = certifications.get(source_period)
        entry = panel_entry_by_period.get(source_period)
        if company is None or product is None or entry is None or entry.pointer_path is None:
            raise ValueError(f"Lagged filing modern source layer incomplete: {source_period}")
        if company.rcept_no != product.rcept_no:
            raise ValueError(f"Lagged filing modern company/product receipt mismatch: {source_period}")
        if company.available_date != product.receipt_date:
            raise ValueError(f"Lagged filing modern receipt-date mismatch: {source_period}")
        if not product.source_vintage_certified or not product.source_archive_bytes_archived:
            raise ValueError(f"Lagged filing modern product source vintage not certified: {source_period}")
        records.append(
            LaggedFilingSourceRecord(
                source_period=source_period,
                target_period=target_period,
                rcept_no=company.rcept_no,
                receipt_date=company.available_date,
                company_revenue_krw=company.revenue_krw,
                company_gross_profit_krw=company.gross_profit_krw,
                company_raw_payload_sha256=company.raw_payload_sha256,
                company_raw_path=str(raw_directory / f"{source_period}.json"),
                product_evidence_id=product.evidence_id,
                product_archive_sha256=product.archive_sha256,
                product_archive_path=str(_modern_product_archive(entry.pointer_path)),
                nand_revenue_krw_million=float(product.metrics.nand_and_solutions),
                other_revenue_krw_million=float(product.metrics.other_products_services),
                product_total_revenue_krw_million=float(
                    product.metrics.reported_company_revenue
                ),
            )
        )
    if tuple(item.source_period for item in records) != contract.expected_source_periods:
        raise ValueError("Lagged filing assembled source-period order drifted")
    return tuple(records)


def certify_lagged_filing_records(
    contract: LaggedFilingCertificationContract,
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
    records: tuple[LaggedFilingSourceRecord, ...],
    *,
    created_at: datetime | None = None,
) -> tuple[LaggedFilingCertificationResult, PointInTimeFeatureBundle]:
    if tuple(item.source_period for item in records) != contract.expected_source_periods:
        raise ValueError("Lagged filing certification records do not match frozen source periods")
    periods = tuple(
        certify_lagged_filing_source_record(contract, protocol, record)
        for record in records
    )
    observations = tuple(item for period in periods for item in period.observations)
    created = created_at or datetime.now(UTC)
    bundle = build_locked_pit_feature_bundle(
        created_at=created,
        observations=observations,
    )
    audit = audit_point_in_time_feature_bundle(protocol, frontier, bundle)
    target_periods = tuple(item.target_period for item in periods)
    gate = (
        target_periods == contract.expected_target_periods
        and len(periods) == contract.expected_target_row_count
        and len(observations) == contract.expected_feature_observation_count
        and audit.eligible_observation_count == contract.expected_feature_observation_count
        and audit.rejected_observation_count == 0
    )
    result = LaggedFilingCertificationResult(
        contract_evidence_id=contract.evidence_id,
        period_certifications=periods,
        certified_target_periods=target_periods,
        certified_target_row_count=len(periods),
        feature_observation_count=len(observations),
        bundle_evidence_id=bundle.evidence_id,
        pit_audit=audit,
        completion_gate_passed=gate,
    )
    if not result.completion_gate_passed:
        raise ValueError("Lagged filing certification completion gate failed")
    return result, bundle


__all__ = [
    "DEFAULT_LAGGED_FILING_BUNDLE",
    "DEFAULT_LAGGED_FILING_CERTIFICATION",
    "DEFAULT_LAGGED_FILING_PIT_OUTPUT",
    "DEFAULT_LAGGED_FILING_REPORT",
    "LaggedFilingCertificationContract",
    "LaggedFilingCertificationResult",
    "LaggedFilingPeriodCertification",
    "LaggedFilingSourceRecord",
    "build_lagged_filing_source_records",
    "build_locked_pit_feature_bundle",
    "certify_lagged_filing_records",
    "certify_lagged_filing_source_record",
    "load_lagged_filing_certification_contract",
    "persist_locked_pit_feature_bundle",
]
