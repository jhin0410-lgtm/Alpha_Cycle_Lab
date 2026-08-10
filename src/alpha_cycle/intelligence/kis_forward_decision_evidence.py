"""Load and attach KIS forward-estimate evidence without changing decision scores."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.kis_forward_estimates import read_json_object

_GENERIC_EXPECTATION_GAP = "컨센서스·실적 추정치 상향·하향 데이터 미연결"
_LEVEL_ONLY_GAP = (
    "시장 컨센서스 출처·추정치 리비전 시계열 미확인 "
    "(KIS forward 실적 추정 level 연결됨)"
)
_CHANGE_AVAILABLE_GAP = (
    "시장 컨센서스 출처 미확인 "
    "(KIS forward 실적 추정 level·snapshot change 연결됨)"
)


@dataclass(frozen=True)
class KisForwardDecisionEvidence:
    artifact_id: str
    source_expectation_snapshot_id: str
    source_expectation_captured_at: datetime
    summaries: pd.DataFrame
    estimates: pd.DataFrame
    change_status: str
    changes: pd.DataFrame
    change_artifact_id: str | None

    def __post_init__(self) -> None:
        _sha256(self.artifact_id, "forward artifact_id")
        _sha256(self.source_expectation_snapshot_id, "source expectation snapshot_id")
        if self.source_expectation_captured_at.tzinfo is None:
            raise ValueError("KIS forward source capture must be timezone-aware")
        if self.change_artifact_id is not None:
            _sha256(self.change_artifact_id, "change artifact_id")
        if self.change_status not in {
            "change_pointer_missing",
            "estimate_change_baseline_only",
            "estimate_snapshot_change_available",
        }:
            raise ValueError("Unexpected KIS estimate change status")

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.summaries["symbol"].astype(str).unique().tolist()))

    @property
    def estimate_snapshot_change_verified(self) -> bool:
        return self.change_status == "estimate_snapshot_change_available"


def _sha256(value: object, field: str) -> str:
    text = str(value).strip()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _aware_datetime(value: object, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _strict_flag(
    mapping: Mapping[str, object],
    key: str,
    expected: bool,
    *,
    label: str,
) -> None:
    if mapping.get(key) is not expected:
        raise ValueError(f"{label} must keep {key}={str(expected).lower()}")


def _inside(directory: Path, candidate: Path, *, label: str) -> Path:
    base = directory.resolve()
    target = candidate.resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside its artifact directory") from exc
    return target


def _pointer_artifact(
    pointer_path: Path,
    *,
    expected_statuses: set[str],
    label: str,
) -> tuple[dict[str, object], dict[str, object], Path]:
    pointer = read_json_object(pointer_path, label=f"{label} pointer")
    status = str(pointer.get("status", "")).strip()
    if status not in expected_statuses:
        raise ValueError(f"{label} pointer status is not usable: {status}")
    directory_text = str(pointer.get("artifact_directory", "")).strip()
    manifest_text = str(pointer.get("manifest_path", "")).strip()
    if not directory_text or not manifest_text:
        raise ValueError(f"{label} pointer is missing artifact paths")
    directory = Path(directory_text)
    if not directory.is_dir():
        raise ValueError(f"{label} artifact directory does not exist")
    manifest_path = _inside(directory, Path(manifest_text), label=f"{label} manifest")
    manifest = read_json_object(manifest_path, label=f"{label} manifest")
    pointer_id = _sha256(pointer.get("artifact_id"), f"{label} pointer artifact_id")
    manifest_id = _sha256(manifest.get("artifact_id"), f"{label} manifest artifact_id")
    if pointer_id != manifest_id:
        raise ValueError(f"{label} pointer and manifest artifact IDs differ")
    if str(manifest.get("status", "")).strip() != status:
        raise ValueError(f"{label} pointer and manifest statuses differ")
    return pointer, manifest, directory


def _bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    values = frame[column]

    def parse(value: object) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().casefold()
        if text in {"true", "1"}:
            return True
        if text in {"false", "0"}:
            return False
        raise ValueError(f"KIS forward evidence {column} contains an invalid boolean")

    return values.map(parse)


def _validate_forward_frame(frame: pd.DataFrame, *, summary: bool) -> pd.DataFrame:
    required = {
        "symbol",
        "period_label",
        "fiscal_year",
        "historical_semantic_crosscheck_verified",
        "provider_semantics_certified",
        "consensus_certified",
        "revision_certified",
        "decision_score_enabled",
    }
    if summary:
        required.update(
            {
                "revenue_krw",
                "operating_income_krw",
                "net_income_attributable_to_owners_krw",
                "operating_margin_pct",
            }
        )
    else:
        required.update(
            {
                "metric",
                "value_krw",
                "growth_from_previous_pct",
                "growth_comparable",
            }
        )
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"KIS forward evidence is missing columns: {sorted(missing)}")
    result = frame.copy()
    result["symbol"] = result["symbol"].astype("string").str.zfill(6)
    if result["symbol"].isna().any() or result["symbol"].eq("").any():
        raise ValueError("KIS forward evidence symbols cannot be blank")
    result["period_label"] = result["period_label"].astype("string")
    result["fiscal_year"] = pd.to_numeric(result["fiscal_year"], errors="raise").astype(int)
    key = ["symbol", "period_label"] if summary else ["symbol", "metric", "period_label"]
    if result.duplicated(key).any():
        raise ValueError("KIS forward evidence contains duplicate rows")
    for column, expected in (
        ("historical_semantic_crosscheck_verified", True),
        ("provider_semantics_certified", False),
        ("consensus_certified", False),
        ("revision_certified", False),
        ("decision_score_enabled", False),
    ):
        if not _bool_series(result, column).eq(expected).all():
            raise ValueError(
                f"KIS forward evidence must keep {column}={str(expected).lower()}"
            )
    numeric = (
        [
            "revenue_krw",
            "operating_income_krw",
            "net_income_attributable_to_owners_krw",
            "operating_margin_pct",
        ]
        if summary
        else ["value_krw"]
    )
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="raise")
        finite = result[column].dropna().map(lambda value: math.isfinite(float(value)))
        if not finite.all():
            raise ValueError(f"KIS forward evidence {column} must be finite")
    return result.sort_values(key, kind="stable").reset_index(drop=True)


def _validate_change_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    required = {
        "symbol",
        "metric",
        "period_label",
        "previous_value_krw",
        "current_value_krw",
        "absolute_change_krw",
        "percent_change",
        "direction",
        "estimate_snapshot_change_verified",
        "provider_semantics_certified",
        "consensus_certified",
        "consensus_revision_certified",
        "revision_certified",
        "decision_score_enabled",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"KIS estimate changes are missing columns: {sorted(missing)}")
    result = frame.copy()
    result["symbol"] = result["symbol"].astype("string").str.zfill(6)
    if result.duplicated(["symbol", "metric", "period_label"]).any():
        raise ValueError("KIS estimate changes contain duplicate rows")
    for column, expected in (
        ("estimate_snapshot_change_verified", True),
        ("provider_semantics_certified", False),
        ("consensus_certified", False),
        ("consensus_revision_certified", False),
        ("revision_certified", False),
        ("decision_score_enabled", False),
    ):
        if not _bool_series(result, column).eq(expected).all():
            raise ValueError(f"KIS estimate changes must keep {column}={str(expected).lower()}")
    directions = set(result["direction"].astype(str))
    if not directions.issubset({"up", "down", "unchanged"}):
        raise ValueError("KIS estimate changes contain an invalid direction")
    return result.sort_values(
        ["symbol", "metric", "period_label"],
        kind="stable",
    ).reset_index(drop=True)


def load_kis_forward_decision_evidence(
    forward_pointer_path: str | Path,
    *,
    change_pointer_path: str | Path | None = None,
) -> KisForwardDecisionEvidence:
    """Load normalized KIS forward levels and an optional aligned snapshot-change artifact."""

    forward_pointer, forward_manifest, forward_directory = _pointer_artifact(
        Path(forward_pointer_path),
        expected_statuses={"forward_estimate_levels_normalized"},
        label="KIS forward estimates",
    )
    for key, expected in (
        ("historical_semantic_crosscheck_verified", True),
        ("forward_values_normalized", True),
        ("provider_semantics_certified", False),
        ("consensus_certified", False),
        ("revision_certified", False),
        ("point_in_time_backtest_eligible", False),
        ("decision_score_enabled", False),
    ):
        _strict_flag(forward_manifest, key, expected, label="KIS forward manifest")
    source_id = _sha256(
        forward_manifest.get("source_expectation_snapshot_id"),
        "KIS forward source expectation snapshot_id",
    )
    source_captured_at = _aware_datetime(
        forward_manifest.get("source_expectation_captured_at"),
        field="KIS forward source expectation captured_at",
    )
    summary_path = _inside(
        forward_directory,
        Path(str(forward_pointer.get("forward_summary_path", ""))),
        label="KIS forward summary",
    )
    estimates_path = _inside(
        forward_directory,
        Path(str(forward_pointer.get("forward_estimates_path", ""))),
        label="KIS forward estimates",
    )
    summaries = _validate_forward_frame(
        pd.read_csv(summary_path, dtype={"symbol": "string"}),
        summary=True,
    )
    estimates = _validate_forward_frame(
        pd.read_csv(estimates_path, dtype={"symbol": "string"}),
        summary=False,
    )

    change_status = "change_pointer_missing"
    changes = pd.DataFrame()
    change_artifact_id: str | None = None
    if change_pointer_path is not None and Path(change_pointer_path).is_file():
        change_pointer, change_manifest, change_directory = _pointer_artifact(
            Path(change_pointer_path),
            expected_statuses={
                "estimate_change_baseline_only",
                "estimate_snapshot_change_available",
            },
            label="KIS forward estimate changes",
        )
        for key, expected in (
            ("provider_semantics_certified", False),
            ("consensus_certified", False),
            ("consensus_revision_certified", False),
            ("revision_certified", False),
            ("point_in_time_backtest_eligible", False),
            ("decision_score_enabled", False),
        ):
            _strict_flag(change_manifest, key, expected, label="KIS change manifest")
        current_source = _sha256(
            change_manifest.get("current_source_expectation_snapshot_id"),
            "KIS change current source snapshot_id",
        )
        if current_source != source_id:
            raise ValueError("KIS change artifact does not describe the latest forward snapshot")
        change_status = str(change_manifest.get("status", ""))
        change_artifact_id = _sha256(
            change_manifest.get("artifact_id"),
            "KIS change artifact_id",
        )
        change_path = _inside(
            change_directory,
            Path(str(change_pointer.get("estimate_changes_path", ""))),
            label="KIS estimate changes",
        )
        raw_changes = pd.read_csv(change_path, dtype={"symbol": "string"})
        changes = _validate_change_frame(raw_changes)
        expected_change = change_status == "estimate_snapshot_change_available"
        if bool(change_manifest.get("estimate_snapshot_change_verified")) != expected_change:
            raise ValueError("KIS change verification flag is inconsistent with status")
        if expected_change and changes.empty:
            raise ValueError("Verified KIS estimate snapshot change has no comparison rows")
        if not expected_change and not changes.empty:
            raise ValueError("Baseline-only KIS estimate change artifact must contain no rows")

    return KisForwardDecisionEvidence(
        artifact_id=_sha256(forward_manifest.get("artifact_id"), "forward artifact_id"),
        source_expectation_snapshot_id=source_id,
        source_expectation_captured_at=source_captured_at,
        summaries=summaries,
        estimates=estimates,
        change_status=change_status,
        changes=changes,
        change_artifact_id=change_artifact_id,
    )


def _json_records(frame: pd.DataFrame) -> str:
    records: list[dict[str, object]] = []
    for raw in frame.to_dict(orient="records"):
        row: dict[str, object] = {}
        for key, value in raw.items():
            if value is None or value is pd.NA or pd.isna(value):
                row[str(key)] = None
            elif hasattr(value, "item"):
                row[str(key)] = value.item()
            else:
                row[str(key)] = value
        records.append(row)
    return json.dumps(records, ensure_ascii=False, sort_keys=True)


def attach_kis_forward_to_scorecards(
    scorecards: pd.DataFrame,
    evidence: KisForwardDecisionEvidence,
) -> pd.DataFrame:
    """Attach forward levels/change context without touching any score component."""

    if "ticker" not in scorecards.columns:
        raise ValueError("Scorecards must contain ticker")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    rows: list[dict[str, object]] = []
    applicable = set(evidence.symbols)
    for raw in result.to_dict(orient="records"):
        row = {str(key): value for key, value in raw.items()}
        ticker = str(row["ticker"])
        available = ticker in applicable
        row["kis_forward_evidence_available"] = available
        row["kis_forward_decision_score_enabled"] = False
        if available:
            company_summary = evidence.summaries.loc[
                evidence.summaries["symbol"].astype(str).eq(ticker)
            ]
            company_estimates = evidence.estimates.loc[
                evidence.estimates["symbol"].astype(str).eq(ticker)
            ]
            company_changes = (
                evidence.changes.loc[evidence.changes["symbol"].astype(str).eq(ticker)]
                if not evidence.changes.empty
                else evidence.changes
            )
            row["kis_forward_artifact_id"] = evidence.artifact_id
            row["kis_forward_source_snapshot_id"] = evidence.source_expectation_snapshot_id
            row["kis_forward_source_captured_at"] = evidence.source_expectation_captured_at.isoformat()
            row["kis_forward_periods_json"] = json.dumps(
                sorted(company_summary["period_label"].astype(str).unique().tolist()),
                ensure_ascii=False,
            )
            row["kis_forward_summary_json"] = _json_records(company_summary)
            row["kis_forward_estimates_json"] = _json_records(company_estimates)
            row["kis_estimate_change_status"] = evidence.change_status
            row["kis_estimate_changes_json"] = _json_records(company_changes)
            row["kis_estimate_snapshot_change_verified"] = (
                evidence.estimate_snapshot_change_verified
            )
        else:
            row["kis_estimate_change_status"] = "not_applicable"
            row["kis_estimate_snapshot_change_verified"] = False
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)


def reconcile_expectation_evidence_gaps(scorecards: pd.DataFrame) -> pd.DataFrame:
    """Narrow, but never erase, the unresolved consensus/revision provenance gap."""

    required = {
        "kis_forward_evidence_available",
        "kis_estimate_snapshot_change_verified",
        "evidence_gaps",
    }
    if not required.issubset(scorecards.columns):
        return scorecards.copy()
    result = scorecards.copy()
    reconciled: list[object] = []
    for raw in result.to_dict(orient="records"):
        available = bool(raw.get("kis_forward_evidence_available"))
        if not available or not isinstance(raw.get("evidence_gaps"), str):
            reconciled.append(raw.get("evidence_gaps"))
            continue
        try:
            parsed: object = json.loads(cast(str, raw["evidence_gaps"]))
        except (TypeError, ValueError):
            reconciled.append(raw.get("evidence_gaps"))
            continue
        if not isinstance(parsed, list):
            reconciled.append(raw.get("evidence_gaps"))
            continue
        replacement = (
            _CHANGE_AVAILABLE_GAP
            if bool(raw.get("kis_estimate_snapshot_change_verified"))
            else _LEVEL_ONLY_GAP
        )
        updated = [
            replacement if str(item) == _GENERIC_EXPECTATION_GAP else str(item)
            for item in parsed
        ]
        reconciled.append(json.dumps(list(dict.fromkeys(updated)), ensure_ascii=False))
    result["evidence_gaps"] = pd.Series(reconciled, index=result.index, dtype="object")
    return result


def sync_record_forward_fields(
    records: pd.DataFrame,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    fields = [
        "ticker",
        "evidence_gaps",
        "kis_forward_evidence_available",
        "kis_forward_artifact_id",
        "kis_forward_source_snapshot_id",
        "kis_forward_source_captured_at",
        "kis_forward_periods_json",
        "kis_estimate_change_status",
        "kis_estimate_snapshot_change_verified",
        "kis_forward_decision_score_enabled",
    ]
    available_fields = [field for field in fields if field in scorecards.columns]
    supplement = scorecards.loc[:, available_fields].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    if supplement["ticker"].duplicated().any():
        raise ValueError("KIS forward scorecards contain duplicate tickers")
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [field for field in available_fields if field != "ticker" and field in result.columns]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _krw_trillion(value: object) -> str:
    number = float(value)
    return f"{number / 1_000_000_000_000:.2f}조원"


def append_kis_forward_report(
    report: str,
    evidence: KisForwardDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## KIS forward 실적 추정 증거 (비점수)",
        "",
        f"- source snapshot: `{evidence.source_expectation_snapshot_id[:12]}`",
        f"- source captured at: `{evidence.source_expectation_captured_at.isoformat()}`",
        f"- forward artifact: `{evidence.artifact_id[:12]}`",
        f"- estimate snapshot change: `{evidence.change_status}`",
        "- 역사 실적 교차검증으로 row/단위 mapping은 확인했지만, 시장 컨센서스 출처·집계 방법은 인증되지 않았습니다.",
        "- 아래 증거는 의사결정 점수를 변경하지 않습니다.",
    ]
    growth_lookup: dict[tuple[str, str, str], object] = {}
    for raw in evidence.estimates.to_dict(orient="records"):
        growth_lookup[(str(raw["symbol"]), str(raw["period_label"]), str(raw["metric"]))] = raw.get(
            "growth_from_previous_pct"
        )
    for ticker in evidence.symbols:
        lines.extend(["", f"### {ticker}", "", "| 기간 | 매출 | 영업이익 | 지배주주순이익 | 영업이익률 | 매출 성장 | 영업이익 성장 |", "|---|---:|---:|---:|---:|---:|---:|"])
        company = evidence.summaries.loc[
            evidence.summaries["symbol"].astype(str).eq(ticker)
        ].sort_values("fiscal_year", kind="stable")
        for raw in company.to_dict(orient="records"):
            period = str(raw["period_label"])
            revenue_growth = growth_lookup.get((ticker, period, "revenue"))
            operating_growth = growth_lookup.get((ticker, period, "operating_income"))
            revenue_growth_text = (
                "n/a" if revenue_growth is None or pd.isna(revenue_growth) else f"{float(revenue_growth):+.1f}%"
            )
            operating_growth_text = (
                "n/a" if operating_growth is None or pd.isna(operating_growth) else f"{float(operating_growth):+.1f}%"
            )
            lines.append(
                "| "
                f"{period} | {_krw_trillion(raw['revenue_krw'])} | "
                f"{_krw_trillion(raw['operating_income_krw'])} | "
                f"{_krw_trillion(raw['net_income_attributable_to_owners_krw'])} | "
                f"{float(raw['operating_margin_pct']):.1f}% | "
                f"{revenue_growth_text} | {operating_growth_text} |"
            )
        if evidence.estimate_snapshot_change_verified:
            company_changes = evidence.changes.loc[
                evidence.changes["symbol"].astype(str).eq(ticker)
            ]
            if not company_changes.empty:
                lines.extend(["", "- 최근 KIS snapshot change"])
                for raw in company_changes.to_dict(orient="records"):
                    pct = raw.get("percent_change")
                    pct_text = "n/a" if pct is None or pd.isna(pct) else f"{float(pct):+.2f}%"
                    lines.append(
                        f"  - {raw['period_label']} {raw['metric']}: "
                        f"{raw['direction']} ({pct_text})"
                    )
        else:
            lines.extend(
                [
                    "",
                    "- snapshot change: 아직 서로 다른 KIS source snapshot이 2개 이상 확인되지 않아 baseline-only입니다.",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "KisForwardDecisionEvidence",
    "append_kis_forward_report",
    "attach_kis_forward_to_scorecards",
    "load_kis_forward_decision_evidence",
    "reconcile_expectation_evidence_gaps",
    "sync_record_forward_fields",
]
