"""Validate KOSIS semiconductor history and bridge it to issuer-cycle evidence.

This module is deliberately descriptive and non-scoring. It validates one immutable
KOSIS history artifact, blocks retroactive use before its capture date, checks freshness,
and compares the industry diagnostic with the already-existing issuer-observed proxy.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.semiconductor_cycle_proxy import SemiconductorCycleProxy

SOURCE_SCOPE = "kosis_semiconductor_industry_evidence"
DEFAULT_MAX_PERIOD_AGE_MONTHS = 4
_EXPECTED_SERIES_COUNT = 9
_SUPPORTED_DIAGNOSTIC_SCHEMA_VERSIONS = frozenset({1, 2})
_METRIC_KEYS = (
    "production_yoy_pct",
    "shipment_yoy_pct",
    "inventory_yoy_pct",
    "capacity_yoy_pct",
    "utilization_yoy_pct",
    "production_mom_sa_pct",
    "shipment_mom_sa_pct",
    "inventory_mom_sa_pct",
    "utilization_mom_sa_pct",
    "shipment_minus_inventory_yoy_pp",
    "production_minus_shipment_yoy_pp",
    "inventory_vs_shipment_index_ratio",
)
_EXPANSION_PHASES = frozenset(
    {
        "recovery_destocking",
        "expansion_inventory_controlled",
        "expansion_inventory_balanced",
        "expansion_inventory_build",
    }
)
_CONTRACTION_PHASES = frozenset(
    {
        "contraction_destocking",
        "demand_slowdown_inventory_build",
    }
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_json(path: Path, *, label: str) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], raw)


def _strict_false(mapping: Mapping[str, object], key: str, *, label: str) -> None:
    if mapping.get(key) is not False:
        raise ValueError(f"{label} must keep {key}=false")


def _strict_true(mapping: Mapping[str, object], key: str, *, label: str) -> None:
    if mapping.get(key) is not True:
        raise ValueError(f"{label} must keep {key}=true")


def _month_index(period: str) -> int:
    if len(period) != 6 or not period.isdigit():
        raise ValueError(f"KOSIS latest period must use YYYYMM: {period!r}")
    year = int(period[:4])
    month = int(period[4:])
    if month < 1 or month > 12:
        raise ValueError(f"KOSIS latest period contains invalid month: {period!r}")
    return year * 12 + month - 1


def _finite_optional(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"KOSIS latest diagnostic {field} must be numeric or null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"KOSIS latest diagnostic {field} must be finite")
    return result


def _industry_direction(phase: str) -> str:
    if phase in _EXPANSION_PHASES:
        return "expansionary"
    if phase in _CONTRACTION_PHASES:
        return "contractionary"
    return "mixed"


def _issuer_direction(state: str) -> str:
    if state.startswith("issuer_expansion"):
        return "expansionary"
    if state == "issuer_contraction":
        return "contractionary"
    return "mixed"


def _alignment(industry_direction: str, issuer_direction: str) -> str:
    if industry_direction == issuer_direction == "expansionary":
        return "industry_issuer_expansion_aligned"
    if industry_direction == issuer_direction == "contractionary":
        return "industry_issuer_contraction_aligned"
    if "mixed" in {industry_direction, issuer_direction}:
        return "industry_issuer_alignment_unresolved"
    return "industry_issuer_divergent"


@dataclass(frozen=True)
class SemiconductorIndustryEvidence:
    source_scope: str
    artifact_id: str
    captured_at: datetime
    latest_period: str
    period_age_months: int
    heuristic_phase: str
    metrics: dict[str, float | None]
    revision_sensitive: bool
    historical_vintage_certified: bool
    point_in_time_backtest_eligible: bool
    heuristic_phase_certified: bool
    industry_cycle_certified: bool
    decision_score_enabled: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "source_scope": self.source_scope,
            "artifact_id": self.artifact_id,
            "captured_at": self.captured_at.isoformat(),
            "latest_period": self.latest_period,
            "period_age_months": self.period_age_months,
            "heuristic_phase": self.heuristic_phase,
            "metrics": dict(self.metrics),
            "revision_sensitive": self.revision_sensitive,
            "historical_vintage_certified": self.historical_vintage_certified,
            "point_in_time_backtest_eligible": self.point_in_time_backtest_eligible,
            "heuristic_phase_certified": self.heuristic_phase_certified,
            "industry_cycle_certified": self.industry_cycle_certified,
            "decision_score_enabled": self.decision_score_enabled,
        }


@dataclass(frozen=True)
class SemiconductorCycleBridge:
    industry: SemiconductorIndustryEvidence
    issuer_state: str
    industry_direction: str
    issuer_direction: str
    alignment_state: str

    def as_dict(self) -> dict[str, object]:
        return {
            "industry": self.industry.as_dict(),
            "issuer_state": self.issuer_state,
            "industry_direction": self.industry_direction,
            "issuer_direction": self.issuer_direction,
            "alignment_state": self.alignment_state,
            "decision_score_enabled": False,
        }


def load_semiconductor_industry_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    max_period_age_months: int = DEFAULT_MAX_PERIOD_AGE_MONTHS,
) -> SemiconductorIndustryEvidence:
    """Load one current KOSIS artifact without granting historical PIT eligibility."""

    if max_period_age_months < 0:
        raise ValueError("max_period_age_months cannot be negative")
    pointer = _read_json(Path(pointer_path), label="KOSIS semiconductor history pointer")
    if pointer.get("status") != "semiconductor_history_captured":
        raise ValueError("KOSIS semiconductor history pointer is not a captured artifact")
    if pointer.get("diagnostics_status") != "heuristic_diagnostics_available":
        raise ValueError("KOSIS semiconductor history diagnostics are unavailable")
    if pointer.get("series_count") != _EXPECTED_SERIES_COUNT:
        raise ValueError("KOSIS semiconductor history must contain exactly nine series")
    _strict_true(pointer, "revision_sensitive", label="KOSIS pointer")
    for key in (
        "historical_vintage_certified",
        "point_in_time_backtest_eligible",
        "heuristic_phase_certified",
        "industry_cycle_certified",
        "decision_score_enabled",
    ):
        _strict_false(pointer, key, label="KOSIS pointer")

    artifact_id = str(pointer.get("artifact_id", "")).strip()
    if len(artifact_id) != 64 or any(ch not in "0123456789abcdef" for ch in artifact_id):
        raise ValueError("KOSIS semiconductor artifact_id must be a SHA-256 digest")
    artifact_directory = Path(str(pointer.get("artifact_directory", "")).strip())
    if not str(artifact_directory):
        raise ValueError("KOSIS semiconductor pointer is missing artifact_directory")
    manifest_path = Path(str(pointer.get("manifest_path", "")).strip())
    diagnostics_path = Path(str(pointer.get("diagnostics_path", "")).strip())
    expected_manifest = artifact_directory / "manifest.json"
    expected_diagnostics = artifact_directory / "diagnostics.json"
    if manifest_path.resolve() != expected_manifest.resolve():
        raise ValueError("KOSIS manifest path is not bound to artifact_directory")
    if diagnostics_path.resolve() != expected_diagnostics.resolve():
        raise ValueError("KOSIS diagnostics path is not bound to artifact_directory")

    manifest = _read_json(manifest_path, label="KOSIS semiconductor manifest")
    diagnostics = _read_json(diagnostics_path, label="KOSIS semiconductor diagnostics")
    if manifest.get("artifact_id") != artifact_id:
        raise ValueError("KOSIS pointer and manifest artifact IDs differ")
    if manifest.get("status") != "semiconductor_history_captured":
        raise ValueError("KOSIS manifest has unexpected status")
    if manifest.get("source") != "kosis_openapi":
        raise ValueError("KOSIS manifest has unexpected source")
    if manifest.get("source_scope") != "korean_semiconductor_cycle_history":
        raise ValueError("KOSIS manifest has unexpected source scope")
    if manifest.get("org_id") != "101":
        raise ValueError("KOSIS manifest has unexpected organization ID")
    _strict_true(manifest, "revision_sensitive", label="KOSIS manifest")
    for key in (
        "historical_vintage_certified",
        "point_in_time_backtest_eligible",
        "heuristic_phase_certified",
        "industry_cycle_certified",
        "decision_score_enabled",
    ):
        _strict_false(manifest, key, label="KOSIS manifest")

    manifest_without_id = dict(manifest)
    manifest_without_id.pop("artifact_id", None)
    recomputed_artifact_id = hashlib.sha256(_canonical_bytes(manifest_without_id)).hexdigest()
    if recomputed_artifact_id != artifact_id:
        raise ValueError("KOSIS semiconductor manifest content hash does not match artifact_id")
    expected_diagnostics_hash = str(manifest.get("diagnostics_sha256", "")).strip()
    actual_diagnostics_hash = hashlib.sha256(_canonical_bytes(diagnostics)).hexdigest()
    if expected_diagnostics_hash != actual_diagnostics_hash:
        raise ValueError("KOSIS semiconductor diagnostics hash does not match manifest")

    series = manifest.get("series")
    if not isinstance(series, list) or len(series) != _EXPECTED_SERIES_COUNT:
        raise ValueError("KOSIS semiconductor manifest must bind all nine series")
    diagnostic_schema = diagnostics.get("schema_version")
    if diagnostic_schema not in _SUPPORTED_DIAGNOSTIC_SCHEMA_VERSIONS:
        raise ValueError(
            "KOSIS diagnostics schema version is unsupported: "
            f"{diagnostic_schema!r}"
        )
    if diagnostics.get("status") != "heuristic_diagnostics_available":
        raise ValueError("KOSIS diagnostics have unexpected status")
    for key in (
        "heuristic_phase_certified",
        "industry_cycle_certified",
        "decision_score_enabled",
    ):
        _strict_false(diagnostics, key, label="KOSIS diagnostics")

    latest_raw = diagnostics.get("latest")
    if not isinstance(latest_raw, dict):
        raise ValueError("KOSIS diagnostics are missing latest observation")
    latest = cast(Mapping[str, object], latest_raw)
    latest_period = str(latest.get("period", "")).strip()
    if latest_period != str(pointer.get("latest_period", "")).strip():
        raise ValueError("KOSIS pointer and diagnostics latest periods differ")

    captured_at_text = str(manifest.get("captured_at", "")).strip()
    try:
        captured_at = datetime.fromisoformat(captured_at_text)
    except ValueError as exc:
        raise ValueError("KOSIS manifest captured_at is invalid") from exc
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("KOSIS manifest captured_at must be timezone-aware")
    if evaluation_date < captured_at.date():
        raise ValueError("KOSIS current snapshot cannot be applied before its capture date")

    evaluation_period = f"{evaluation_date.year:04d}{evaluation_date.month:02d}"
    age_months = _month_index(evaluation_period) - _month_index(latest_period)
    if age_months < 0:
        raise ValueError("KOSIS latest period cannot be after the decision evaluation month")
    if age_months > max_period_age_months:
        raise ValueError(
            "KOSIS semiconductor industry evidence is stale: "
            f"age_months={age_months} max={max_period_age_months}"
        )

    phase = str(latest.get("heuristic_phase", "")).strip()
    if phase not in _EXPANSION_PHASES | _CONTRACTION_PHASES:
        raise ValueError(f"KOSIS semiconductor heuristic phase is unsupported: {phase!r}")
    metrics = {
        key: _finite_optional(latest.get(key), field=key)
        for key in _METRIC_KEYS
    }
    return SemiconductorIndustryEvidence(
        source_scope=SOURCE_SCOPE,
        artifact_id=artifact_id,
        captured_at=captured_at,
        latest_period=latest_period,
        period_age_months=age_months,
        heuristic_phase=phase,
        metrics=metrics,
        revision_sensitive=True,
        historical_vintage_certified=False,
        point_in_time_backtest_eligible=False,
        heuristic_phase_certified=False,
        industry_cycle_certified=False,
        decision_score_enabled=False,
    )


def build_semiconductor_cycle_bridge(
    proxy: SemiconductorCycleProxy,
    industry: SemiconductorIndustryEvidence,
) -> SemiconductorCycleBridge:
    industry_direction = _industry_direction(industry.heuristic_phase)
    issuer_direction = _issuer_direction(proxy.cycle_proxy_state)
    return SemiconductorCycleBridge(
        industry=industry,
        issuer_state=proxy.cycle_proxy_state,
        industry_direction=industry_direction,
        issuer_direction=issuer_direction,
        alignment_state=_alignment(industry_direction, issuer_direction),
    )


def attach_semiconductor_industry_to_scorecards(
    scorecards: pd.DataFrame,
    proxy: SemiconductorCycleProxy,
    bridge: SemiconductorCycleBridge,
) -> pd.DataFrame:
    """Attach sector evidence while preserving every pre-existing score value."""

    if "ticker" not in scorecards.columns:
        raise ValueError("Scorecards must contain ticker")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    applicable = result["ticker"].isin(proxy.expected_tickers)
    result["industry_evidence_available"] = applicable
    result["industry_evidence_artifact_id"] = None
    result["industry_evidence_latest_period"] = None
    result["industry_heuristic_phase"] = None
    result["industry_evidence_age_months"] = None
    result["industry_issuer_alignment"] = None
    result["industry_evidence_score_enabled"] = False
    result.loc[applicable, "industry_evidence_artifact_id"] = bridge.industry.artifact_id
    result.loc[applicable, "industry_evidence_latest_period"] = bridge.industry.latest_period
    result.loc[applicable, "industry_heuristic_phase"] = bridge.industry.heuristic_phase
    result.loc[applicable, "industry_evidence_age_months"] = bridge.industry.period_age_months
    result.loc[applicable, "industry_issuer_alignment"] = bridge.alignment_state
    for key, value in bridge.industry.metrics.items():
        column = f"industry_{key}"
        result[column] = None
        result.loc[applicable, column] = value
    result["industry_evidence_json"] = None
    result.loc[applicable, "industry_evidence_json"] = json.dumps(
        bridge.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
    )
    return result


def attach_semiconductor_industry_to_records(
    records: pd.DataFrame,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "ticker",
        "industry_evidence_available",
        "industry_evidence_artifact_id",
        "industry_evidence_latest_period",
        "industry_heuristic_phase",
        "industry_evidence_age_months",
        "industry_issuer_alignment",
        "industry_evidence_score_enabled",
    ]
    missing = [column for column in columns if column not in scorecards.columns]
    if missing:
        raise ValueError("Scorecards are missing industry evidence fields: " + ",".join(missing))
    supplement = scorecards.loc[:, columns].copy()
    return records.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _fmt(value: float | None, *, suffix: str = "%") -> str:
    return "N/A" if value is None else f"{value:+.2f}{suffix}"


def append_semiconductor_industry_evidence_report(
    report: str,
    bridge: SemiconductorCycleBridge,
) -> str:
    metrics = bridge.industry.metrics
    lines = [
        report.rstrip(),
        "",
        "## KOSIS 반도체 산업 사이클 증거 (비점수)",
        "",
        f"- KOSIS 기준월: `{bridge.industry.latest_period}` / "
        f"평가월 대비 {bridge.industry.period_age_months}개월 지연",
        f"- 산업 휴리스틱: `{bridge.industry.heuristic_phase}` "
        f"({bridge.industry_direction})",
        f"- 발행사 프록시: `{bridge.issuer_state}` ({bridge.issuer_direction})",
        f"- 산업↔발행사 정합성: `{bridge.alignment_state}`",
        f"- artifact: `{bridge.industry.artifact_id[:12]}`",
        "- 이 KOSIS 스냅샷은 revision-sensitive이며 historical vintage가 아닙니다. "
        "capture date 이전 평가에 소급 적용할 수 없습니다.",
        "- 산업 국면 라벨은 검증된 예측모형이 아니며 의사결정 점수에는 반영하지 않습니다.",
        "",
        "| 생산 YoY | 출하 YoY | 재고 YoY | 출하-재고 YoY spread | 생산능력 YoY | 가동률 YoY |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        "| "
        + " | ".join(
            [
                _fmt(metrics.get("production_yoy_pct")),
                _fmt(metrics.get("shipment_yoy_pct")),
                _fmt(metrics.get("inventory_yoy_pct")),
                _fmt(metrics.get("shipment_minus_inventory_yoy_pp"), suffix="%p"),
                _fmt(metrics.get("capacity_yoy_pct")),
                _fmt(metrics.get("utilization_yoy_pct")),
            ]
        )
        + " |",
        "",
        "| 생산 SA MoM | 출하 SA MoM | 재고 SA MoM | 가동률 SA MoM |",
        "| ---: | ---: | ---: | ---: |",
        "| "
        + " | ".join(
            [
                _fmt(metrics.get("production_mom_sa_pct")),
                _fmt(metrics.get("shipment_mom_sa_pct")),
                _fmt(metrics.get("inventory_mom_sa_pct")),
                _fmt(metrics.get("utilization_mom_sa_pct")),
            ]
        )
        + " |",
    ]
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_MAX_PERIOD_AGE_MONTHS",
    "SemiconductorCycleBridge",
    "SemiconductorIndustryEvidence",
    "append_semiconductor_industry_evidence_report",
    "attach_semiconductor_industry_to_records",
    "attach_semiconductor_industry_to_scorecards",
    "build_semiconductor_cycle_bridge",
    "load_semiconductor_industry_evidence",
]
