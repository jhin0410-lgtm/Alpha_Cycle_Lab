"""Freeze the exact twenty-row SK hynix ex-ante development scope target-blind.

This layer bridges source-only PIT panel construction and the first historical target join.
It consumes only the completed expansion report and locked PIT feature bundle, then binds
immutable evidence identities, the exact period set, feature schema, and preregistered
estimator geometry. It never loads historical targets, fits a model, runs a backtest, or
opens the protected 2026Q3 outcome.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    load_frozen_ex_ante_estimator_selection,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER,
    ExAnteFeatureFrontier,
    load_ex_ante_feature_frontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    PointInTimeFeatureBundle,
    load_point_in_time_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_expansion import (
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION,
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT,
    load_frozen_pit_panel_expansion_contract,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    FrozenCompanyGPExAnteProtocol,
    load_frozen_company_gp_ex_ante_protocol,
)

DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-scope-freeze"
)
DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE = (
    DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE_OUTPUT / "latest_scope_freeze.json"
)

_EXPECTED_TARGET_PERIODS = tuple(
    f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3)
)
_EXPECTED_ADDED_TARGET_PERIODS = (
    "2021Q2",
    "2021Q3",
    "2022Q2",
    "2022Q3",
    "2016Q2",
    "2016Q3",
)
_EXPECTED_FEATURE_IDS = (
    "lagged_company_revenue",
    "lagged_company_gross_profit",
    "lagged_company_gross_margin",
    "lagged_nand_revenue_share",
    "lagged_other_revenue_share",
)
_STATUS = "skhynix_ex_ante_exact_twenty_period_scope_frozen_target_blind"
_NEXT_ACTION = "perform_first_historical_target_join_against_exact_frozen_scope"
_EXPANSION_STATUS = "skhynix_ex_ante_pit_panel_expansion_complete_target_blind"
_EXPANSION_NEXT_ACTION = (
    "refreeze_exact_twenty_period_ex_ante_scope_before_first_target_join"
)


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


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _json_object(path: Path, label: str) -> tuple[bytes, dict[str, object]]:
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    try:
        raw: object = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid UTF-8 JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return raw_bytes, {
        str(key): value for key, value in cast(dict[object, object], raw).items()
    }


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {
        str(key): item for key, item in cast(dict[object, object], value).items()
    }


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _aware_datetime(value: object, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return result


@dataclass(frozen=True)
class FrozenExactTwentyPeriodExAnteScope:
    evidence_id: str
    frozen_at: datetime
    status: str
    ticker: str
    target_metric: str
    protocol_evidence_id: str
    feature_frontier_evidence_id: str
    estimator_freeze_evidence_id: str
    expansion_contract_evidence_id: str
    expansion_report_sha256: str
    base_bundle_evidence_id: str
    combined_bundle_evidence_id: str
    target_periods: tuple[str, ...]
    feature_ids: tuple[str, ...]
    target_row_count: int
    feature_observation_count: int
    selected_legacy_year: int
    shared_initial_training_rows: int
    scored_fold_count: int
    all_observations_point_in_time_eligible: bool
    all_frozen_candidates_sample_eligible: bool
    next_action: str
    historical_target_values_read: bool = False
    target_join_authorized: bool = False
    estimator_fit_authorized: bool = False
    historical_backtest_run: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.protocol_evidence_id,
            self.feature_frontier_evidence_id,
            self.estimator_freeze_evidence_id,
            self.expansion_contract_evidence_id,
            self.expansion_report_sha256,
            self.base_bundle_evidence_id,
            self.combined_bundle_evidence_id,
        )
        if any(not _valid_sha(value) for value in hashes):
            raise ValueError("Ex-ante scope freeze evidence bindings must be SHA-256")
        if self.frozen_at.tzinfo is None or self.frozen_at.utcoffset() is None:
            raise ValueError("Ex-ante scope freeze timestamp must be timezone-aware")
        if self.status != _STATUS:
            raise ValueError("Ex-ante scope freeze status drifted")
        if self.ticker != "000660":
            raise ValueError("Ex-ante scope freeze ticker drifted")
        if self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Ex-ante scope freeze target metric drifted")
        if self.target_periods != _EXPECTED_TARGET_PERIODS:
            raise ValueError("Ex-ante scope freeze target periods drifted")
        if self.feature_ids != _EXPECTED_FEATURE_IDS:
            raise ValueError("Ex-ante scope freeze feature schema drifted")
        if self.target_row_count != 20 or self.feature_observation_count != 100:
            raise ValueError("Ex-ante scope freeze panel geometry drifted")
        if self.selected_legacy_year != 2016:
            raise ValueError("Ex-ante scope freeze legacy-year binding drifted")
        if self.shared_initial_training_rows != 12 or self.scored_fold_count != 8:
            raise ValueError("Ex-ante scope freeze chronological geometry drifted")
        if not self.all_observations_point_in_time_eligible:
            raise ValueError("Ex-ante scope freeze contains non-PIT observations")
        if not self.all_frozen_candidates_sample_eligible:
            raise ValueError("Ex-ante scope freeze does not satisfy every frozen candidate")
        if self.next_action != _NEXT_ACTION:
            raise ValueError("Ex-ante scope freeze next action drifted")
        prohibited = (
            self.historical_target_values_read,
            self.target_join_authorized,
            self.estimator_fit_authorized,
            self.historical_backtest_run,
            self.q3_target_read,
            self.q3_source_outcome_loaded,
        )
        if any(prohibited):
            raise ValueError("Ex-ante scope freeze exceeded target-blind boundary")


def _scope_payload(scope: FrozenExactTwentyPeriodExAnteScope) -> dict[str, object]:
    return {
        "frozen_at": scope.frozen_at.isoformat(),
        "status": scope.status,
        "ticker": scope.ticker,
        "target_metric": scope.target_metric,
        "protocol_evidence_id": scope.protocol_evidence_id,
        "feature_frontier_evidence_id": scope.feature_frontier_evidence_id,
        "estimator_freeze_evidence_id": scope.estimator_freeze_evidence_id,
        "expansion_contract_evidence_id": scope.expansion_contract_evidence_id,
        "expansion_report_sha256": scope.expansion_report_sha256,
        "base_bundle_evidence_id": scope.base_bundle_evidence_id,
        "combined_bundle_evidence_id": scope.combined_bundle_evidence_id,
        "target_periods": list(scope.target_periods),
        "feature_ids": list(scope.feature_ids),
        "target_row_count": scope.target_row_count,
        "feature_observation_count": scope.feature_observation_count,
        "selected_legacy_year": scope.selected_legacy_year,
        "shared_initial_training_rows": scope.shared_initial_training_rows,
        "scored_fold_count": scope.scored_fold_count,
        "all_observations_point_in_time_eligible": (
            scope.all_observations_point_in_time_eligible
        ),
        "all_frozen_candidates_sample_eligible": (
            scope.all_frozen_candidates_sample_eligible
        ),
        "next_action": scope.next_action,
        "historical_target_values_read": scope.historical_target_values_read,
        "target_join_authorized": scope.target_join_authorized,
        "estimator_fit_authorized": scope.estimator_fit_authorized,
        "historical_backtest_run": scope.historical_backtest_run,
        "q3_target_read": scope.q3_target_read,
        "q3_source_outcome_loaded": scope.q3_source_outcome_loaded,
    }


def _validate_expansion_report(
    root: dict[str, object],
    *,
    expansion_contract_evidence_id: str,
    base_bundle_evidence_id: str,
    combined_bundle_evidence_id: str,
) -> None:
    if root.get("schema_version") != 1 or root.get("status") != _EXPANSION_STATUS:
        raise ValueError("Ex-ante scope freeze requires a completed expansion report")
    result = _mapping(root.get("result"), "PIT expansion report result")
    exact_pairs = {
        "contract_evidence_id": expansion_contract_evidence_id,
        "base_bundle_evidence_id": base_bundle_evidence_id,
        "combined_bundle_evidence_id": combined_bundle_evidence_id,
        "status": _EXPANSION_STATUS,
        "next_action": _EXPANSION_NEXT_ACTION,
    }
    for key, expected in exact_pairs.items():
        if result.get(key) != expected:
            raise ValueError(f"Ex-ante scope freeze expansion report {key} drifted")
    if result.get("selected_legacy_year") != 2016:
        raise ValueError("Ex-ante scope freeze requires the successful 2016 legacy pair")
    added_periods = tuple(
        str(item)
        for item in _array(result.get("added_target_periods"), "added_target_periods")
    )
    combined_periods = tuple(
        str(item)
        for item in _array(
            result.get("combined_target_periods"),
            "combined_target_periods",
        )
    )
    if added_periods != _EXPECTED_ADDED_TARGET_PERIODS:
        raise ValueError("Ex-ante scope freeze added target-period order drifted")
    if combined_periods != _EXPECTED_TARGET_PERIODS:
        raise ValueError("Ex-ante scope freeze combined target-period scope drifted")
    numeric_expectations = {
        "added_target_row_count": 6,
        "added_feature_observation_count": 30,
        "combined_target_row_count": 20,
        "combined_feature_observation_count": 100,
        "eligible_added_observation_count": 30,
        "rejected_added_observation_count": 0,
    }
    for key, expected in numeric_expectations.items():
        if result.get(key) != expected:
            raise ValueError(f"Ex-ante scope freeze expansion report {key} drifted")
    required_true = (
        "all_added_observations_point_in_time_eligible",
        "completion_gate_passed",
    )
    if any(result.get(key) is not True for key in required_true):
        raise ValueError("Ex-ante scope freeze expansion completion gate is not closed")
    required_false = (
        "historical_target_values_read",
        "target_join_authorized",
        "estimator_fit_authorized",
        "historical_backtest_run",
        "q3_target_read",
        "q3_source_outcome_loaded",
    )
    if any(result.get(key) is not False for key in required_false):
        raise ValueError("Ex-ante scope freeze expansion report opened a target boundary")
    attempts = _array(result.get("attempts"), "PIT expansion attempts")
    if not attempts:
        raise ValueError("Ex-ante scope freeze expansion report lacks source attempts")
    for raw_attempt in attempts:
        attempt = _mapping(raw_attempt, "PIT expansion source attempt")
        for key in ("target_value_read", "estimator_fit_run", "backtest_run"):
            if attempt.get(key) is not False:
                raise ValueError(
                    "Ex-ante scope freeze source replay crossed its target-blind boundary"
                )


def _validate_bundle_scope(
    bundle: PointInTimeFeatureBundle,
    *,
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
) -> None:
    if bundle.target_values_included:
        raise ValueError("Ex-ante scope freeze bundle unexpectedly contains target values")
    if len(bundle.observations) != 100:
        raise ValueError("Ex-ante scope freeze bundle must contain exactly 100 observations")

    feature_map = frontier.by_id()
    by_period: dict[str, list[str]] = {}
    rejected: list[str] = []
    for observation in bundle.observations:
        by_period.setdefault(observation.period_id, []).append(observation.feature_id)
        feature = feature_map.get(observation.feature_id)
        if feature is None:
            rejected.append(
                f"{observation.period_id}:{observation.feature_id}:unknown_feature"
            )
            continue
        if observation.provenance_class not in feature.acceptable_provenance_classes:
            rejected.append(
                f"{observation.period_id}:{observation.feature_id}:provenance_not_allowed"
            )
        origin = protocol.origin_for(observation.period_id)
        if observation.source_available_at > origin:
            rejected.append(
                f"{observation.period_id}:{observation.feature_id}:source_after_origin"
            )
        if observation.target_metric_in_payload:
            rejected.append(
                f"{observation.period_id}:{observation.feature_id}:target_in_payload"
            )
        if observation.provenance_class == "current_retrieval_only":
            rejected.append(
                f"{observation.period_id}:{observation.feature_id}:current_retrieval_only"
            )
        if observation.provenance_class == "prospective_snapshot":
            if observation.captured_at is None:
                rejected.append(
                    f"{observation.period_id}:{observation.feature_id}:missing_capture_time"
                )
            else:
                if observation.captured_at > origin:
                    rejected.append(
                        f"{observation.period_id}:{observation.feature_id}:capture_after_origin"
                    )
                if observation.source_available_at > observation.captured_at:
                    rejected.append(
                        f"{observation.period_id}:{observation.feature_id}:capture_before_source"
                    )
    periods = tuple(sorted(by_period))
    if periods != _EXPECTED_TARGET_PERIODS:
        raise ValueError("Ex-ante scope freeze bundle target-period set drifted")
    for period_id in _EXPECTED_TARGET_PERIODS:
        if tuple(by_period.get(period_id, ())) != _EXPECTED_FEATURE_IDS:
            raise ValueError(
                f"Ex-ante scope freeze feature schema drifted for period: {period_id}"
            )
    if rejected:
        details = ", ".join(rejected[:5])
        raise ValueError(
            f"Ex-ante scope freeze PIT audit rejected observations: {details}"
        )


def build_exact_twenty_period_ex_ante_scope_freeze(
    *,
    expansion_report_path: str | Path = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT,
    combined_bundle_path: str | Path = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
    expansion_contract_path: str | Path = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION,
    protocol_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    feature_frontier_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER,
    estimator_freeze_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    frozen_at: datetime | None = None,
) -> FrozenExactTwentyPeriodExAnteScope:
    """Bind the completed twenty-row PIT panel before any historical target join."""

    expansion = load_frozen_pit_panel_expansion_contract(expansion_contract_path)
    protocol = load_frozen_company_gp_ex_ante_protocol(protocol_path)
    frontier = load_ex_ante_feature_frontier(feature_frontier_path)
    estimator = load_frozen_ex_ante_estimator_selection(estimator_freeze_path)
    if expansion.estimator_freeze_evidence_id != estimator.evidence_id:
        raise ValueError("Ex-ante scope freeze estimator binding drifted from expansion")
    if estimator.required_rows_before_first_target_join != 20:
        raise ValueError("Ex-ante scope freeze estimator row floor drifted")
    if estimator.feature_ids != _EXPECTED_FEATURE_IDS:
        raise ValueError("Ex-ante scope freeze estimator feature schema drifted")

    report_bytes, report = _json_object(
        Path(expansion_report_path),
        "PIT expansion report",
    )
    bundle = load_point_in_time_feature_bundle(combined_bundle_path)
    _validate_expansion_report(
        report,
        expansion_contract_evidence_id=expansion.evidence_id,
        base_bundle_evidence_id=expansion.base_bundle_evidence_id,
        combined_bundle_evidence_id=bundle.evidence_id,
    )
    _validate_bundle_scope(bundle, protocol=protocol, frontier=frontier)

    row_count = len({item.period_id for item in bundle.observations})
    shared_scored_folds = row_count - estimator.shared_initial_training_rows
    all_candidates_ready = all(
        row_count >= item.required_total_rows_for_eight_folds_if_scored_alone
        for item in estimator.candidates
    )
    if row_count != 20 or shared_scored_folds != estimator.minimum_scored_folds:
        raise ValueError("Ex-ante scope freeze chronological scored-fold geometry drifted")
    if not all_candidates_ready:
        raise ValueError("Ex-ante scope freeze has a sample-ineligible frozen candidate")

    provisional = FrozenExactTwentyPeriodExAnteScope(
        evidence_id="0" * 64,
        frozen_at=frozen_at or datetime.now(UTC),
        status=_STATUS,
        ticker=protocol.ticker,
        target_metric=protocol.target_metric,
        protocol_evidence_id=protocol.evidence_id,
        feature_frontier_evidence_id=frontier.evidence_id,
        estimator_freeze_evidence_id=estimator.evidence_id,
        expansion_contract_evidence_id=expansion.evidence_id,
        expansion_report_sha256=_sha_bytes(report_bytes),
        base_bundle_evidence_id=expansion.base_bundle_evidence_id,
        combined_bundle_evidence_id=bundle.evidence_id,
        target_periods=_EXPECTED_TARGET_PERIODS,
        feature_ids=_EXPECTED_FEATURE_IDS,
        target_row_count=row_count,
        feature_observation_count=len(bundle.observations),
        selected_legacy_year=2016,
        shared_initial_training_rows=estimator.shared_initial_training_rows,
        scored_fold_count=shared_scored_folds,
        all_observations_point_in_time_eligible=True,
        all_frozen_candidates_sample_eligible=all_candidates_ready,
        next_action=_NEXT_ACTION,
    )
    return replace(provisional, evidence_id=_sha(_scope_payload(provisional)))


def persist_exact_twenty_period_ex_ante_scope_freeze(
    scope: FrozenExactTwentyPeriodExAnteScope,
    path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE,
) -> Path:
    """Persist a hash-named immutable freeze plus a replayable latest pointer."""

    if _sha(_scope_payload(scope)) != scope.evidence_id:
        raise ValueError("Ex-ante scope freeze evidence hash drifted before persistence")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": _STATUS,
        "scope": {"evidence_id": scope.evidence_id, **_scope_payload(scope)},
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    immutable = output.parent / f"scope-{scope.evidence_id}.json"
    if immutable.exists():
        if immutable.read_bytes() != encoded:
            raise ValueError("Ex-ante scope freeze immutable evidence file drifted")
    else:
        immutable.write_bytes(encoded)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(output)
    reloaded = load_frozen_exact_twenty_period_ex_ante_scope(output)
    if reloaded.evidence_id != scope.evidence_id:
        raise ValueError("Ex-ante scope freeze failed exact persistence replay")
    return output


def load_frozen_exact_twenty_period_ex_ante_scope(
    path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE,
) -> FrozenExactTwentyPeriodExAnteScope:
    _raw_bytes, root = _json_object(Path(path), "Ex-ante scope freeze")
    if root.get("schema_version") != 1 or root.get("status") != _STATUS:
        raise ValueError("Ex-ante scope freeze artifact status is invalid")
    body = _mapping(root.get("scope"), "Ex-ante scope freeze body")
    false_keys = (
        "historical_target_values_read",
        "target_join_authorized",
        "estimator_fit_authorized",
        "historical_backtest_run",
        "q3_target_read",
        "q3_source_outcome_loaded",
    )
    if any(body.get(key) is not False for key in false_keys):
        raise ValueError("Ex-ante scope freeze artifact opened a prohibited trust flag")
    scope = FrozenExactTwentyPeriodExAnteScope(
        evidence_id=str(body.get("evidence_id", "")),
        frozen_at=_aware_datetime(body.get("frozen_at"), "scope.frozen_at"),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        target_metric=str(body.get("target_metric", "")),
        protocol_evidence_id=str(body.get("protocol_evidence_id", "")),
        feature_frontier_evidence_id=str(
            body.get("feature_frontier_evidence_id", "")
        ),
        estimator_freeze_evidence_id=str(
            body.get("estimator_freeze_evidence_id", "")
        ),
        expansion_contract_evidence_id=str(
            body.get("expansion_contract_evidence_id", "")
        ),
        expansion_report_sha256=str(body.get("expansion_report_sha256", "")),
        base_bundle_evidence_id=str(body.get("base_bundle_evidence_id", "")),
        combined_bundle_evidence_id=str(
            body.get("combined_bundle_evidence_id", "")
        ),
        target_periods=tuple(
            str(item)
            for item in _array(body.get("target_periods"), "target_periods")
        ),
        feature_ids=tuple(
            str(item) for item in _array(body.get("feature_ids"), "feature_ids")
        ),
        target_row_count=int(str(body.get("target_row_count", -1))),
        feature_observation_count=int(
            str(body.get("feature_observation_count", -1))
        ),
        selected_legacy_year=int(str(body.get("selected_legacy_year", -1))),
        shared_initial_training_rows=int(
            str(body.get("shared_initial_training_rows", -1))
        ),
        scored_fold_count=int(str(body.get("scored_fold_count", -1))),
        all_observations_point_in_time_eligible=(
            body.get("all_observations_point_in_time_eligible") is True
        ),
        all_frozen_candidates_sample_eligible=(
            body.get("all_frozen_candidates_sample_eligible") is True
        ),
        next_action=str(body.get("next_action", "")),
        historical_target_values_read=False,
        target_join_authorized=False,
        estimator_fit_authorized=False,
        historical_backtest_run=False,
        q3_target_read=False,
        q3_source_outcome_loaded=False,
    )
    if _sha(_scope_payload(scope)) != scope.evidence_id:
        raise ValueError("Ex-ante scope freeze evidence hash mismatch")
    return scope


__all__ = [
    "DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE",
    "DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE_OUTPUT",
    "FrozenExactTwentyPeriodExAnteScope",
    "build_exact_twenty_period_ex_ante_scope_freeze",
    "load_frozen_exact_twenty_period_ex_ante_scope",
    "persist_exact_twenty_period_ex_ante_scope_freeze",
]
