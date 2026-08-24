"""Canonical source-chain revalidation for persisted Decision System v2.1 package evidence.

A derived artifact is not trusted merely because its own typed payload, manifest and content
address are valid.  This module reconstructs the persisted source contracts and reruns the
canonical builder so forged-but-self-consistent derived envelopes fail closed.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import (
    EpistemicStatus,
    InvestmentThesisSnapshot,
)
from alpha_cycle.intelligence.epistemic_defense import (
    EPISTEMIC_DEFENSE_SCHEMA_VERSION,
    BlindSpotCandidate,
    BlindSpotDiscoverySnapshot,
    CounterExplanation,
    CounterThesisSnapshot,
    CounterThesisStatus,
    EpistemicDefensePackageSnapshot,
    MaterialityLevel,
    PromotionRecommendation,
    UnresolvedContradiction,
    build_epistemic_defense_package,
)
from alpha_cycle.intelligence.expectation_state import ExpectationStateSnapshot
from alpha_cycle.intelligence.forward_valuation import (
    ForwardValuationMetric,
    ForwardValuationStateSnapshot,
    build_forward_valuation_state,
)
from alpha_cycle.intelligence.price_implied_requirement import (
    PRICE_IMPLIED_SCHEMA_VERSION,
    PriceImpliedRequirementSnapshot,
    ReferenceFrameKind,
    ValuationReferenceFrameSnapshot,
    ValuationReferencePoint,
    build_price_implied_requirement,
)
from alpha_cycle.intelligence.valuation import (
    VALUATION_SCHEMA_VERSION,
    ValuationEvidenceSnapshot,
    _records,
    _valuation_metrics,
)
from alpha_cycle.research_package_integrity_v2_1 import require_trusted_artifact_root


class ResearchPackageSourceRevalidationError(ValueError):
    """Raised when a referenced source repository violates the trusted-root contract."""


def forward_valuation_sources_are_canonical(
    root: str | Path,
    *,
    snapshot: ForwardValuationStateSnapshot,
    expectations: ExpectationStateSnapshot,
) -> bool:
    """Rebuild a forward-valuation snapshot from its persisted PIT market-cap source."""

    artifact_root = Path(root)
    valuation = load_canonical_valuation_evidence(
        artifact_root,
        snapshot.valuation_evidence_snapshot_id,
    )
    if valuation is None:
        return False
    try:
        rebuilt = build_forward_valuation_state(
            valuation,
            expectations,
            captured_at=snapshot.captured_at,
            guardrails=load_decision_system_v21_guardrails(),
        )
    except (TypeError, ValueError):
        return False
    return bool(
        rebuilt.snapshot_id == snapshot.snapshot_id
        and rebuilt.payload_without_id() == snapshot.payload_without_id()
    )


def price_implied_sources_are_canonical(
    root: str | Path,
    *,
    snapshot: PriceImpliedRequirementSnapshot,
) -> bool:
    """Rebuild a price-implied requirement from valuation and reference-frame sources."""
    artifact_root = Path(root)
    valuation = load_canonical_valuation_evidence(
        artifact_root,
        snapshot.valuation_evidence_snapshot_id,
    )
    reference_frame = load_canonical_valuation_reference_frame(
        artifact_root,
        snapshot.reference_frame_snapshot_id,
    )
    if valuation is None or reference_frame is None:
        return False
    try:
        rebuilt = build_price_implied_requirement(
            valuation,
            reference_frame,
            captured_at=snapshot.captured_at,
            guardrails=load_decision_system_v21_guardrails(),
        )
    except (TypeError, ValueError):
        return False
    return bool(
        rebuilt.snapshot_id == snapshot.snapshot_id
        and rebuilt.payload_without_id() == snapshot.payload_without_id()
    )


def epistemic_package_sources_are_canonical(
    root: str | Path,
    *,
    thesis: InvestmentThesisSnapshot,
    snapshot: EpistemicDefensePackageSnapshot,
) -> bool:
    """Rebuild an epistemic-defense package from its independent research contracts."""

    artifact_root = Path(root)
    counter = load_canonical_counter_thesis(
        artifact_root,
        snapshot.counter_thesis_snapshot_id,
    )
    blind_spot = load_canonical_blind_spot(
        artifact_root,
        snapshot.blind_spot_snapshot_id,
    )
    if counter is None or blind_spot is None:
        return False
    try:
        rebuilt = build_epistemic_defense_package(
            thesis,
            counter,
            blind_spot,
            captured_at=snapshot.captured_at,
            guardrails=load_decision_system_v21_guardrails(),
        )
    except (TypeError, ValueError):
        return False
    return bool(
        rebuilt.snapshot_id == snapshot.snapshot_id
        and rebuilt.payload_without_id() == snapshot.payload_without_id()
    )


def load_canonical_counter_thesis(
    root: Path,
    snapshot_id: str,
) -> CounterThesisSnapshot | None:
    envelope = _load_content_addressed_envelope(
        root,
        repository_name="counter_thesis",
        snapshot_id=snapshot_id,
        payload_name="counter_thesis.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        explanations = tuple(
            CounterExplanation(
                explanation_id=_text(item, "explanation_id"),
                statement=_text(item, "statement"),
                mechanism=_text(item, "mechanism"),
                epistemic_status=EpistemicStatus(_text(item, "epistemic_status")),
                materiality=MaterialityLevel(_text(item, "materiality")),
                supporting_evidence_refs=_text_tuple(item, "supporting_evidence_refs"),
                opposing_evidence_refs=_text_tuple(item, "opposing_evidence_refs"),
                falsifier=_text(item, "falsifier"),
            )
            for item in _object_list(payload, "alternative_explanations")
        )
        contradictions = tuple(
            UnresolvedContradiction(
                contradiction_id=_text(item, "contradiction_id"),
                statement=_text(item, "statement"),
                materiality=MaterialityLevel(_text(item, "materiality")),
                evidence_refs=_text_tuple(item, "evidence_refs"),
            )
            for item in _object_list(payload, "unresolved_contradictions")
        )
        snapshot = CounterThesisSnapshot(
            counter_thesis_id=_text(payload, "counter_thesis_id"),
            snapshot_version=_integer(payload, "snapshot_version"),
            parent_snapshot_id=_optional_text(payload, "parent_snapshot_id"),
            thesis_snapshot_id=_text(payload, "thesis_snapshot_id"),
            captured_at=_datetime(payload, "captured_at"),
            created_without_thesis_support_search=_boolean(
                payload, "created_without_thesis_support_search"
            ),
            independence_method=_text(payload, "independence_method"),
            search_scope=_text_tuple(payload, "search_scope"),
            strongest_alternative_explanation_id=_text(
                payload, "strongest_alternative_explanation_id"
            ),
            alternative_explanations=explanations,
            falsification_evidence_refs=_text_tuple(payload, "falsification_evidence_refs"),
            missing_evidence=_text_tuple(payload, "missing_evidence"),
            unresolved_contradictions=contradictions,
            status=CounterThesisStatus(_text(payload, "status")),
            guardrail_evidence_id=_text(payload, "guardrail_evidence_id"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_manifest = _research_contract_manifest(
        "counter_thesis", snapshot.snapshot_id, snapshot.captured_at
    )
    return (
        snapshot
        if _canonical_simple_snapshot_matches(
            snapshot_id,
            payload,
            manifest,
            directory,
            snapshot.snapshot_id,
            snapshot.captured_at,
            snapshot.payload_without_id(),
            expected_manifest,
        )
        else None
    )


def load_canonical_blind_spot(
    root: Path,
    snapshot_id: str,
) -> BlindSpotDiscoverySnapshot | None:
    envelope = _load_content_addressed_envelope(
        root,
        repository_name="blind_spot",
        snapshot_id=snapshot_id,
        payload_name="blind_spot.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        candidates = tuple(
            BlindSpotCandidate(
                candidate_id=_text(item, "candidate_id"),
                variable=_text(item, "variable"),
                mechanism=_text(item, "mechanism"),
                materiality=MaterialityLevel(_text(item, "materiality")),
                evidence_refs=_text_tuple(item, "evidence_refs"),
                already_covered=_boolean(item, "already_covered"),
                promotion_recommendation=PromotionRecommendation(
                    _text(item, "promotion_recommendation")
                ),
                rationale=_text(item, "rationale"),
            )
            for item in _object_list(payload, "candidates")
        )
        snapshot = BlindSpotDiscoverySnapshot(
            discovery_id=_text(payload, "discovery_id"),
            snapshot_version=_integer(payload, "snapshot_version"),
            parent_snapshot_id=_optional_text(payload, "parent_snapshot_id"),
            thesis_snapshot_id=_text(payload, "thesis_snapshot_id"),
            captured_at=_datetime(payload, "captured_at"),
            existing_critical_state_variables=_text_tuple(
                payload, "existing_critical_state_variables"
            ),
            graph_variables_used_as_exclusion_set=_boolean(
                payload, "graph_variables_used_as_exclusion_set"
            ),
            search_scope=_text_tuple(payload, "search_scope"),
            discovery_method=_text(payload, "discovery_method"),
            search_completed=_boolean(payload, "search_completed"),
            candidates=candidates,
            search_limitations=_text_tuple(payload, "search_limitations"),
            no_candidate_found_reason=_optional_text(payload, "no_candidate_found_reason"),
            guardrail_evidence_id=_text(payload, "guardrail_evidence_id"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_manifest = _research_contract_manifest(
        "blind_spot", snapshot.snapshot_id, snapshot.captured_at
    )
    return (
        snapshot
        if _canonical_simple_snapshot_matches(
            snapshot_id,
            payload,
            manifest,
            directory,
            snapshot.snapshot_id,
            snapshot.captured_at,
            snapshot.payload_without_id(),
            expected_manifest,
        )
        else None
    )


def load_canonical_valuation_reference_frame(
    root: Path,
    snapshot_id: str,
) -> ValuationReferenceFrameSnapshot | None:
    envelope = _load_content_addressed_envelope(
        root,
        repository_name="valuation_reference_frame",
        snapshot_id=snapshot_id,
        payload_name="valuation_reference_frame.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        points = tuple(
            ValuationReferencePoint(
                reference_id=_text(item, "reference_id"),
                metric=_forward_metric(_text(item, "metric")),
                target_period=_text(item, "target_period"),
                target_period_end=_date(item, "target_period_end"),
                reference_multiple=_number(item, "reference_multiple"),
                reference_kind=ReferenceFrameKind(_text(item, "reference_kind")),
                observed_at=_datetime(item, "observed_at"),
                rationale=_text(item, "rationale"),
                source_evidence_ids=_text_tuple(item, "source_evidence_ids"),
            )
            for item in _object_list(payload, "reference_points")
        )
        snapshot = ValuationReferenceFrameSnapshot(
            captured_at=_datetime(payload, "captured_at"),
            evaluation_date=_date(payload, "evaluation_date"),
            security_id=_text(payload, "security_id"),
            reference_points=points,
            source_snapshot_ids=_text_tuple(payload, "source_snapshot_ids"),
            guardrail_evidence_id=_text(payload, "guardrail_evidence_id"),
            warnings=_text_tuple(payload, "warnings"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_manifest = {
        "schema_version": PRICE_IMPLIED_SCHEMA_VERSION,
        "object_type": "valuation_reference_frame",
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "immutable": True,
        "market_expectation_claimed": False,
        "fair_value_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "automatic_execution_enabled": False,
        "files": ["valuation_reference_frame.json"],
    }
    return (
        snapshot
        if _canonical_simple_snapshot_matches(
            snapshot_id,
            payload,
            manifest,
            directory,
            snapshot.snapshot_id,
            snapshot.captured_at,
            snapshot.payload_without_id(),
            expected_manifest,
        )
        else None
    )


def load_canonical_valuation_evidence(
    root: Path,
    snapshot_id: str,
) -> ValuationEvidenceSnapshot | None:
    """Load the legacy CSV-backed valuation evidence under a package-root convention."""

    directory = _find_valuation_directory(root, snapshot_id)
    if directory is None:
        return None
    manifest_path = directory / "manifest.json"
    required_files = (
        "shares.csv",
        "security_values.csv",
        "financial_history.csv",
        "valuation_metrics.csv",
        "raw_valuation.json",
    )
    try:
        manifest = _read_json_regular(manifest_path, root)
        if set(manifest) != {
            "schema_version",
            "snapshot_id",
            "captured_at",
            "evaluation_date",
            "research_snapshot_id",
            "market_snapshot_id",
            "history_years",
            "symbols",
            "market_cap_complete_count",
            "valuation_scored_count",
            "warnings",
            "valuation_method",
            "consensus_available",
            "order_api_enabled",
            "files",
        }:
            return None
        frames = {name: _read_valuation_csv(directory / name, root) for name in required_files[:-1]}
        raw_valuation = _read_json_regular(directory / "raw_valuation.json", root)
        snapshot = ValuationEvidenceSnapshot(
            captured_at=_datetime(manifest, "captured_at"),
            evaluation_date=_date(manifest, "evaluation_date"),
            research_snapshot_id=_text(manifest, "research_snapshot_id"),
            market_snapshot_id=_text(manifest, "market_snapshot_id"),
            history_years=_integer(manifest, "history_years"),
            shares=frames["shares.csv"],
            security_values=frames["security_values.csv"],
            financial_history=frames["financial_history.csv"],
            valuation_metrics=frames["valuation_metrics.csv"],
            raw_valuation=raw_valuation,
            warnings=_text_tuple(manifest, "warnings"),
        )
    except (
        KeyError,
        OSError,
        TypeError,
        ValueError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ):
        return None
    expected_manifest = {
        "schema_version": VALUATION_SCHEMA_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "evaluation_date": snapshot.evaluation_date.isoformat(),
        "research_snapshot_id": snapshot.research_snapshot_id,
        "market_snapshot_id": snapshot.market_snapshot_id,
        "history_years": snapshot.history_years,
        "symbols": snapshot.valuation_metrics["ticker"].astype(str).tolist(),
        "market_cap_complete_count": int(
            snapshot.valuation_metrics["market_cap_complete"].astype(bool).sum()
        ),
        "valuation_scored_count": int(snapshot.valuation_metrics["valuation_score"].notna().sum()),
        "warnings": list(snapshot.warnings),
        "valuation_method": "peer_relative_percentile_shrunk_to_neutral",
        "consensus_available": False,
        "order_api_enabled": False,
        "files": list(required_files),
    }
    if manifest != expected_manifest or snapshot.snapshot_id != snapshot_id:
        return None
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    if directory.name != f"{timestamp}__{snapshot.snapshot_id[:12]}":
        return None
    if not _valuation_evidence_semantics_match(snapshot):
        return None
    return snapshot


def _valuation_evidence_semantics_match(snapshot: ValuationEvidenceSnapshot) -> bool:
    """Recompute market-cap semantics instead of trusting self-consistent CSV values."""

    if not isinstance(snapshot.raw_valuation, dict):
        return False
    if snapshot.raw_valuation.get("source_research_snapshot_id") != snapshot.research_snapshot_id:
        return False
    if snapshot.raw_valuation.get("source_market_snapshot_id") != snapshot.market_snapshot_id:
        return False

    values = snapshot.security_values
    required_value_columns = {
        "ticker",
        "security_name",
        "security_class",
        "issued_shares",
        "price",
        "security_market_value",
        "priced",
    }
    required_share_columns = {
        "ticker",
        "security_name",
        "security_class",
        "issued_shares",
    }
    if not required_value_columns.issubset(values.columns):
        return False
    if not required_share_columns.issubset(snapshot.shares.columns):
        return False

    def finite_or_none(value: object) -> float | None:
        if value is None:
            return None
        try:
            result = float(cast(float | int | str, value))
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    def key(row: dict[str, object]) -> tuple[str, str, str, float | None]:
        return (
            str(row.get("ticker", "")).strip(),
            str(row.get("security_name", "")).strip(),
            str(row.get("security_class", "")).strip(),
            finite_or_none(row.get("issued_shares")),
        )

    share_keys = {
        key({str(name): value for name, value in row.items()})
        for row in snapshot.shares.to_dict(orient="records")
    }
    for raw in values.to_dict(orient="records"):
        row = {str(name): value for name, value in raw.items()}
        if key(row) not in share_keys:
            return False
        issued = finite_or_none(row.get("issued_shares"))
        price = finite_or_none(row.get("price"))
        observed_value = finite_or_none(row.get("security_market_value"))
        raw_priced = row.get("priced")
        if not isinstance(raw_priced, (bool, np.bool_)):
            return False
        expected_priced = price is not None
        if bool(raw_priced) is not expected_priced:
            return False
        expected_value = price * issued if price is not None and issued is not None else None
        if expected_value is None:
            if observed_value is not None:
                return False
        elif observed_value is None or not math.isclose(
            observed_value, expected_value, rel_tol=1e-12, abs_tol=1e-6
        ):
            return False

    try:
        recomputed = _valuation_metrics(values, snapshot.financial_history)
        if _records(recomputed.reset_index(drop=True)) != _records(
            snapshot.valuation_metrics.reset_index(drop=True)
        ):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _find_valuation_directory(root: Path, snapshot_id: str) -> Path | None:
    resolved_root = require_trusted_artifact_root(root)
    matches: list[Path] = []
    for repository_name in ("valuation_evidence", "valuation"):
        repository = root / repository_name
        if not repository.exists():
            continue
        if repository.is_symlink() or not repository.is_dir():
            raise ResearchPackageSourceRevalidationError(
                f"{repository_name} repository must be a regular directory"
            )
        resolved_repository = repository.resolve()
        if resolved_repository.parent != resolved_root:
            raise ResearchPackageSourceRevalidationError(
                f"{repository_name} repository escapes artifact_root"
            )
        for candidate in repository.iterdir():
            if not candidate.name.endswith(f"__{snapshot_id[:12]}"):
                continue
            if candidate.is_symlink() or not candidate.is_dir():
                raise ResearchPackageSourceRevalidationError(
                    "valuation snapshot directory must be a regular directory"
                )
            if candidate.resolve().parent != resolved_repository:
                raise ResearchPackageSourceRevalidationError(
                    "valuation snapshot directory escapes repository"
                )
            manifest = _read_json_regular(candidate / "manifest.json", root)
            if str(manifest.get("snapshot_id", "")) == snapshot_id:
                matches.append(candidate)
    if len(matches) > 1:
        raise ResearchPackageSourceRevalidationError(
            "valuation evidence identity is ambiguous across trusted repositories"
        )
    return matches[0] if matches else None


def _load_content_addressed_envelope(
    root: Path,
    *,
    repository_name: str,
    snapshot_id: str,
    payload_name: str,
) -> tuple[dict[str, object], dict[str, object], Path] | None:
    resolved_root = require_trusted_artifact_root(root)
    repository = root / repository_name
    if not repository.exists():
        return None
    if repository.is_symlink() or not repository.is_dir():
        raise ResearchPackageSourceRevalidationError(
            f"{repository_name} repository must be a regular directory"
        )
    resolved_repository = repository.resolve()
    if resolved_repository.parent != resolved_root:
        raise ResearchPackageSourceRevalidationError(
            f"{repository_name} repository escapes artifact_root"
        )
    matches = []
    for candidate in repository.iterdir():
        if not candidate.name.endswith(f"__{snapshot_id[:12]}"):
            continue
        if candidate.is_symlink() or not candidate.is_dir():
            raise ResearchPackageSourceRevalidationError(
                f"{repository_name} snapshot must be a regular directory"
            )
        if candidate.resolve().parent != resolved_repository:
            raise ResearchPackageSourceRevalidationError(
                f"{repository_name} snapshot escapes repository"
            )
        manifest = _read_json_regular(candidate / "manifest.json", root)
        if str(manifest.get("snapshot_id", "")) == snapshot_id:
            matches.append(candidate)
    if len(matches) > 1:
        raise ResearchPackageSourceRevalidationError(
            f"duplicate {repository_name} snapshot identity"
        )
    if not matches:
        return None
    directory = matches[0]
    return (
        _read_json_regular(directory / payload_name, root),
        _read_json_regular(directory / "manifest.json", root),
        directory,
    )


def _canonical_simple_snapshot_matches(
    requested_id: str,
    payload: dict[str, object],
    manifest: dict[str, object],
    directory: Path,
    actual_id: str,
    captured_at: datetime,
    canonical_payload: dict[str, object],
    expected_manifest: dict[str, object],
) -> bool:
    if requested_id != actual_id or payload != canonical_payload or manifest != expected_manifest:
        return False
    from datetime import UTC

    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return directory.name == f"{timestamp}__{actual_id[:12]}"


def _research_contract_manifest(
    object_type: str,
    snapshot_id: str,
    captured_at: datetime,
) -> dict[str, object]:
    return {
        "schema_version": EPISTEMIC_DEFENSE_SCHEMA_VERSION,
        "object_type": object_type,
        "snapshot_id": snapshot_id,
        "captured_at": captured_at.isoformat(),
        "immutable": True,
        "decision_score_enabled": False,
        "investability_decision_enabled": False,
        "automatic_execution_enabled": False,
        "files": [f"{object_type}.json"],
    }


def _read_valuation_csv(path: Path, root: Path) -> pd.DataFrame:
    _require_regular_contained_file(path, root)
    header = pd.read_csv(path, nrows=0)
    string_columns = {
        column: "string"
        for column in header.columns
        if column in {"ticker", "stock_code", "corp_code", "report_code", "symbol"}
        or column.endswith("_date")
        or column.endswith("_end")
    }
    return pd.read_csv(path, dtype=string_columns or None)


def _read_json_regular(path: Path, root: Path) -> dict[str, object]:
    _require_regular_contained_file(path, root)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ResearchPackageSourceRevalidationError(f"JSON object required: {path}")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _require_regular_contained_file(path: Path, root: Path) -> None:
    resolved_root = require_trusted_artifact_root(root)
    if path.is_symlink() or not path.is_file():
        raise ResearchPackageSourceRevalidationError(
            f"source evidence file must be a regular file: {path}"
        )
    resolved = path.resolve()
    if resolved_root not in resolved.parents:
        raise ResearchPackageSourceRevalidationError(
            f"source evidence file escapes artifact_root: {path}"
        )


def _forward_metric(value: str) -> ForwardValuationMetric:
    return ForwardValuationMetric(value)


def _text(payload: dict[str, object], field: str) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value


def _optional_text(payload: dict[str, object], field: str) -> str | None:
    value = payload[field]
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text when supplied")
    return value


def _integer(payload: dict[str, object], field: str) -> int:
    value = payload[field]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def _number(payload: dict[str, object], field: str) -> float:
    value = payload[field]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    return float(value)


def _boolean(payload: dict[str, object], field: str) -> bool:
    value = payload[field]
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _datetime(payload: dict[str, object], field: str) -> datetime:
    return datetime.fromisoformat(_text(payload, field))


def _date(payload: dict[str, object], field: str) -> date:
    return date.fromisoformat(_text(payload, field))


def _text_tuple(payload: dict[str, object], field: str) -> tuple[str, ...]:
    value = payload[field]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be an array of strings")
    return tuple(cast(list[str], value))


def _object_list(payload: dict[str, object], field: str) -> tuple[dict[str, object], ...]:
    value = payload[field]
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{field} must be an array of objects")
    return tuple(
        {str(key): item for key, item in raw.items()}
        for raw in cast(list[dict[object, object]], value)
    )


__all__ = [
    "ResearchPackageSourceRevalidationError",
    "epistemic_package_sources_are_canonical",
    "forward_valuation_sources_are_canonical",
    "load_canonical_blind_spot",
    "load_canonical_counter_thesis",
    "load_canonical_valuation_evidence",
    "load_canonical_valuation_reference_frame",
    "price_implied_sources_are_canonical",
]
