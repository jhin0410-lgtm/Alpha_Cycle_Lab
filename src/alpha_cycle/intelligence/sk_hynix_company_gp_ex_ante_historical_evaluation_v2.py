"""Outcome-blind schema repair for the first SK hynix historical target evaluation.

Execution v1 retrieved the exact twenty OpenDART payloads into process memory but failed
before constructing the first target observation because the 2016 H1 revenue concept did
not match the newer ``ifrs-full_*`` namespace. No joined target artifact, estimator fit,
or backtest was produced.

V2 preserves every model-side choice from v1 and expands only standard XBRL concept aliases
across the legacy ``ifrs_*`` and newer ``ifrs-full_*`` namespaces. V2 also locks raw payload
bytes before target extraction. If parsing fails again, later parser repair must replay those
same bytes rather than refreshing outcomes from OpenDART.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    load_frozen_ex_ante_estimator_selection,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation import (
    DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT,
    FrozenHistoricalEvaluationExecution,
    HistoricalBacktestResult,
    HistoricalTargetJoin,
    build_historical_target_join,
    collect_historical_target_payloads,
    load_frozen_historical_evaluation_execution,
    load_historical_target_join,
    persist_historical_backtest,
    persist_historical_target_join,
    run_frozen_historical_backtest,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    load_point_in_time_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_expansion import (
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_scope_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE,
    load_frozen_exact_twenty_period_ex_ante_scope,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION_V2 = Path(
    "config/skhynix_company_gp_ex_ante_historical_evaluation_execution.v2.yaml"
)
DEFAULT_COMPANY_GP_EX_ANTE_RAW_TARGET_CAPTURE = (
    DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT
    / "latest_historical_raw_target_capture.json"
)
_RAW_CAPTURE_STATUS = "skhynix_ex_ante_historical_raw_target_payloads_locked_pre_extraction"
_EXPECTED_PERIODS = tuple(
    f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3)
)
_EXPECTED_REVENUE_IDS = (
    "ifrs_Revenue",
    "ifrs-full_Revenue",
    "ifrs-full_RevenueFromContractsWithCustomers",
)
_EXPECTED_COST_IDS = ("ifrs_CostOfSales", "ifrs-full_CostOfSales")
_EXPECTED_GROSS_IDS = ("ifrs_GrossProfit", "ifrs-full_GrossProfit")
_EXPECTED_FAILURE = "2016 report_code=11012 label=revenue count=0"
_EXPECTED_REPAIR_SCOPE = "xbrl_standard_account_namespace_alias_expansion_only"


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _sha(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class FrozenHistoricalSchemaRepairV2:
    evidence_id: str
    execution_version: str
    status: str
    prior_execution_path: str
    prior_execution_evidence_id: str
    attempted_git_commit: str
    observed_failure_signature: str
    repair_scope: str
    raw_payloads_retrieved_in_v1: bool
    target_observation_constructed_in_v1: bool
    target_join_persisted_in_v1: bool
    estimator_fit_run_in_v1: bool
    historical_backtest_run_in_v1: bool
    outcome_value_inspection_used_for_repair: bool
    raw_capture_before_target_extraction: bool
    raw_capture_reused_after_parser_failure: bool
    revenue_account_ids: tuple[str, ...]
    cost_of_sales_account_ids: tuple[str, ...]
    gross_profit_account_ids: tuple[str, ...]
    runtime_execution: FrozenHistoricalEvaluationExecution

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("Historical schema-repair evidence id must be SHA-256")
        expected_version = "1.1-frozen-after-schema-failure-before-target-resolution"
        if self.execution_version != expected_version:
            raise ValueError("Historical schema-repair execution version drifted")
        if self.status != "frozen_after_schema_failure_before_target_resolution":
            raise ValueError("Historical schema-repair status drifted")
        if not _valid_sha(self.prior_execution_evidence_id):
            raise ValueError("Historical schema-repair prior evidence id is invalid")
        if len(self.attempted_git_commit) != 40:
            raise ValueError("Historical schema-repair attempted commit must be full SHA")
        if self.observed_failure_signature != _EXPECTED_FAILURE:
            raise ValueError("Historical schema-repair failure signature drifted")
        if self.repair_scope != _EXPECTED_REPAIR_SCOPE:
            raise ValueError("Historical schema-repair scope drifted")
        if not self.raw_payloads_retrieved_in_v1:
            raise ValueError("Historical schema-repair must disclose v1 payload retrieval")
        if any(
            (
                self.target_observation_constructed_in_v1,
                self.target_join_persisted_in_v1,
                self.estimator_fit_run_in_v1,
                self.historical_backtest_run_in_v1,
                self.outcome_value_inspection_used_for_repair,
            )
        ):
            raise ValueError("Historical schema-repair crossed a prohibited outcome boundary")
        if not (
            self.raw_capture_before_target_extraction
            and self.raw_capture_reused_after_parser_failure
        ):
            raise ValueError("Historical schema-repair raw-capture gate drifted")
        if self.revenue_account_ids != _EXPECTED_REVENUE_IDS:
            raise ValueError("Historical schema-repair revenue aliases drifted")
        if self.cost_of_sales_account_ids != _EXPECTED_COST_IDS:
            raise ValueError("Historical schema-repair cost aliases drifted")
        if self.gross_profit_account_ids != _EXPECTED_GROSS_IDS:
            raise ValueError("Historical schema-repair gross-profit aliases drifted")
        if self.runtime_execution.evidence_id != self.evidence_id:
            raise ValueError("Historical schema-repair runtime evidence binding drifted")
        if self.runtime_execution.exact_target_periods != _EXPECTED_PERIODS:
            raise ValueError("Historical schema-repair target periods drifted")


@dataclass(frozen=True)
class HistoricalRawTargetCapture:
    evidence_id: str
    execution_evidence_id: str
    evaluation_date: date
    target_periods: tuple[str, ...]
    raw_payload_sha256: tuple[tuple[str, str], ...]
    captured_payload_bytes_sha256: tuple[tuple[str, str], ...]
    status: str = _RAW_CAPTURE_STATUS

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.execution_evidence_id):
            raise ValueError("Historical raw target capture evidence ids must be SHA-256")
        if self.target_periods != _EXPECTED_PERIODS:
            raise ValueError("Historical raw target capture periods drifted")
        if self.status != _RAW_CAPTURE_STATUS:
            raise ValueError("Historical raw target capture status drifted")
        raw_periods = tuple(period for period, _digest in self.raw_payload_sha256)
        byte_periods = tuple(
            period for period, _digest in self.captured_payload_bytes_sha256
        )
        if raw_periods != self.target_periods or byte_periods != self.target_periods:
            raise ValueError("Historical raw target capture hash periods drifted")
        all_hashes = (
            digest
            for _period, digest in (
                *self.raw_payload_sha256,
                *self.captured_payload_bytes_sha256,
            )
        )
        if not all(_valid_sha(digest) for digest in all_hashes):
            raise ValueError("Historical raw target capture contains an invalid hash")


def _load_yaml(path: str | Path, label: str) -> dict[str, object]:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, label)
    if root.get("schema_version") != 1:
        raise ValueError(f"{label} schema is invalid")
    return root


def load_frozen_historical_schema_repair_v2(
    path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION_V2,
) -> FrozenHistoricalSchemaRepairV2:
    root = _load_yaml(path, "Historical schema-repair manifest")
    body = _mapping(root.get("execution"), "Historical schema-repair execution")
    inputs = _mapping(body.get("frozen_inputs"), "Historical schema-repair inputs")
    prior_path = str(inputs.get("prior_execution_path", ""))
    prior_root = _load_yaml(prior_path, "Prior historical execution manifest")
    prior_body = _mapping(prior_root.get("execution"), "Prior historical execution")
    prior = load_frozen_historical_evaluation_execution(prior_path)

    for key in ("exact_target_periods", "preprocessing", "chronological_evaluation"):
        if body.get(key) != prior_body.get(key):
            raise ValueError(f"Historical schema-repair changed frozen model field: {key}")
    if body.get("protected_outcomes") != prior_body.get("protected_outcomes"):
        raise ValueError("Historical schema-repair changed protected outcome policy")
    for key in ("ticker", "target_metric", "scientific_scope"):
        if body.get(key) != prior_body.get(key):
            raise ValueError(f"Historical schema-repair changed frozen execution field: {key}")

    policy = _mapping(body.get("target_source_policy"), "Historical schema-repair policy")
    prior_policy = _mapping(
        prior_body.get("target_source_policy"),
        "Prior historical target-source policy",
    )
    unchanged_source_fields = (
        "provider",
        "endpoint",
        "fs_div",
        "q2_report_code",
        "q3_report_code",
        "current_term_amount_field",
        "allowed_statement_divisions",
        "require_revenue_minus_cost_equals_gross_profit",
        "require_same_receipt_for_selected_accounts",
        "require_receipt_date_not_after_evaluation_date",
        "post_join_target_refresh_allowed",
        "correction_search_or_selection_allowed",
        "source_fallback_allowed",
        "partial_target_join_allowed",
    )
    for key in unchanged_source_fields:
        if policy.get(key) != prior_policy.get(key):
            raise ValueError(f"Historical schema-repair changed source policy field: {key}")

    revenue_ids = tuple(
        str(item) for item in _array(policy.get("revenue_account_ids"), "revenue aliases")
    )
    cost_ids = tuple(
        str(item)
        for item in _array(policy.get("cost_of_sales_account_ids"), "cost aliases")
    )
    gross_ids = tuple(
        str(item)
        for item in _array(policy.get("gross_profit_account_ids"), "gross aliases")
    )
    if revenue_ids != _EXPECTED_REVENUE_IDS:
        raise ValueError("Historical schema-repair revenue alias contract drifted")
    if cost_ids != _EXPECTED_COST_IDS or gross_ids != _EXPECTED_GROSS_IDS:
        raise ValueError("Historical schema-repair cost/gross alias contract drifted")
    if policy.get("raw_payload_capture_before_target_extraction") is not True:
        raise ValueError("Historical schema-repair must capture raw payloads before extraction")
    if policy.get("raw_payload_capture_reused_after_parser_failure") is not True:
        raise ValueError("Historical schema-repair must replay raw capture after parser failure")

    incident = _mapping(body.get("prior_schema_failure"), "Historical schema incident")
    prohibited_drift = (
        "model_scope_changed_after_failure",
        "feature_scope_changed_after_failure",
        "candidate_scope_changed_after_failure",
        "fold_geometry_changed_after_failure",
        "benchmark_or_metric_changed_after_failure",
    )
    if any(incident.get(key) is not False for key in prohibited_drift):
        raise ValueError("Historical schema-repair changed model scope after v1 failure")
    if incident.get("attempt_date") != date(2026, 8, 21):
        raise ValueError("Historical schema-repair incident date drifted")

    trust = _mapping(
        body.get("trust_boundary_before_v2_resolution"),
        "Historical schema-repair trust boundary",
    )
    if trust.get("v1_raw_payload_retrieval_occurred") is not True:
        raise ValueError("Historical schema-repair trust boundary hides v1 retrieval")
    prohibited_trust = (
        "v1_target_observation_constructed",
        "historical_target_join_persisted",
        "estimator_fit_run",
        "historical_backtest_run",
        "final_estimator_selected",
        "numeric_forward_forecast_enabled",
        "fair_value_estimate_enabled",
        "target_price_enabled",
        "decision_score_enabled",
        "investment_action_enabled",
    )
    if any(trust.get(key) is not False for key in prohibited_trust):
        raise ValueError("Historical schema-repair trust boundary opened prohibited state")

    evidence_id = _sha({"schema_version": 1, "execution": body})
    runtime = replace(
        prior,
        evidence_id=evidence_id,
        revenue_account_ids=revenue_ids,
        cost_of_sales_account_ids=cost_ids,
        gross_profit_account_ids=gross_ids,
    )
    return FrozenHistoricalSchemaRepairV2(
        evidence_id=evidence_id,
        execution_version=str(body.get("execution_version", "")),
        status=str(body.get("status", "")),
        prior_execution_path=prior_path,
        prior_execution_evidence_id=prior.evidence_id,
        attempted_git_commit=str(incident.get("attempted_git_commit", "")),
        observed_failure_signature=str(incident.get("observed_failure_signature", "")),
        repair_scope=str(incident.get("repair_scope", "")),
        raw_payloads_retrieved_in_v1=(
            incident.get("raw_opendart_payloads_retrieved_into_process_memory") is True
        ),
        target_observation_constructed_in_v1=(
            incident.get("target_observation_constructed") is True
        ),
        target_join_persisted_in_v1=(
            incident.get("historical_target_join_persisted") is True
        ),
        estimator_fit_run_in_v1=incident.get("estimator_fit_run") is True,
        historical_backtest_run_in_v1=(
            incident.get("historical_backtest_run") is True
        ),
        outcome_value_inspection_used_for_repair=(
            incident.get("outcome_value_inspection_used_for_repair") is True
        ),
        raw_capture_before_target_extraction=(
            policy.get("raw_payload_capture_before_target_extraction") is True
        ),
        raw_capture_reused_after_parser_failure=(
            policy.get("raw_payload_capture_reused_after_parser_failure") is True
        ),
        revenue_account_ids=revenue_ids,
        cost_of_sales_account_ids=cost_ids,
        gross_profit_account_ids=gross_ids,
        runtime_execution=runtime,
    )


def _raw_capture_payload(capture: HistoricalRawTargetCapture) -> dict[str, object]:
    return {
        "execution_evidence_id": capture.execution_evidence_id,
        "evaluation_date": capture.evaluation_date.isoformat(),
        "target_periods": list(capture.target_periods),
        "raw_payload_sha256": [list(item) for item in capture.raw_payload_sha256],
        "captured_payload_bytes_sha256": [
            list(item) for item in capture.captured_payload_bytes_sha256
        ],
        "status": capture.status,
    }


def persist_historical_raw_target_capture(
    execution: FrozenHistoricalEvaluationExecution,
    *,
    evaluation_date: date,
    raw_payloads: dict[str, object],
    output: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT,
) -> tuple[HistoricalRawTargetCapture, Path]:
    if tuple(raw_payloads) != execution.exact_target_periods:
        raise ValueError("Historical raw target capture requires exact frozen period order")
    raw_hashes = tuple(
        (period, _sha(raw_payloads[period])) for period in execution.exact_target_periods
    )
    byte_hashes = tuple(
        (period, _sha_bytes(_canonical_json_bytes(raw_payloads[period])))
        for period in execution.exact_target_periods
    )
    provisional = HistoricalRawTargetCapture(
        evidence_id="0" * 64,
        execution_evidence_id=execution.evidence_id,
        evaluation_date=evaluation_date,
        target_periods=execution.exact_target_periods,
        raw_payload_sha256=raw_hashes,
        captured_payload_bytes_sha256=byte_hashes,
    )
    capture = replace(
        provisional,
        evidence_id=_sha(_raw_capture_payload(provisional)),
    )
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    pointer = root / "latest_historical_raw_target_capture.json"
    if pointer.exists():
        existing, _payloads = load_historical_raw_target_capture(pointer)
        if existing.evidence_id != capture.evidence_id:
            raise ValueError("Historical raw target capture is already locked and cannot refresh")
        return existing, pointer

    artifact = root / f"raw-capture-{capture.evidence_id}"
    temporary = root / f".{artifact.name}.tmp"
    if artifact.exists() or temporary.exists():
        raise ValueError("Historical raw target capture artifact path already exists")
    temporary.mkdir()
    try:
        raw_root = temporary / "raw"
        raw_root.mkdir()
        for period in execution.exact_target_periods:
            (raw_root / f"{period}.json").write_bytes(
                _canonical_json_bytes(raw_payloads[period])
            )
        artifact_payload = {
            "schema_version": 1,
            "status": _RAW_CAPTURE_STATUS,
            "capture": {
                "evidence_id": capture.evidence_id,
                **_raw_capture_payload(capture),
            },
        }
        (temporary / "capture.json").write_bytes(
            _canonical_json_bytes(artifact_payload)
        )
        temporary.rename(artifact)
        pointer_payload = {
            **artifact_payload,
            "artifact_directory": str(artifact.resolve()),
        }
        pointer_tmp = root / ".latest_historical_raw_target_capture.json.tmp"
        pointer_tmp.write_bytes(_canonical_json_bytes(pointer_payload))
        pointer_tmp.replace(pointer)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    replayed, _payloads = load_historical_raw_target_capture(pointer)
    if replayed.evidence_id != capture.evidence_id:
        raise ValueError("Historical raw target capture failed exact persistence replay")
    return replayed, pointer


def load_historical_raw_target_capture(
    path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_RAW_TARGET_CAPTURE,
) -> tuple[HistoricalRawTargetCapture, dict[str, object]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "Historical raw target capture artifact")
    if root.get("schema_version") != 1 or root.get("status") != _RAW_CAPTURE_STATUS:
        raise ValueError("Historical raw target capture artifact status is invalid")
    body = _mapping(root.get("capture"), "Historical raw target capture body")

    def pairs(key: str) -> tuple[tuple[str, str], ...]:
        result: list[tuple[str, str]] = []
        for raw_pair in _array(body.get(key), key):
            pair = _array(raw_pair, f"{key} pair")
            if len(pair) != 2:
                raise ValueError(f"Historical raw target capture {key} pair is invalid")
            result.append((str(pair[0]), str(pair[1])))
        return tuple(result)

    capture = HistoricalRawTargetCapture(
        evidence_id=str(body.get("evidence_id", "")),
        execution_evidence_id=str(body.get("execution_evidence_id", "")),
        evaluation_date=date.fromisoformat(str(body.get("evaluation_date", ""))),
        target_periods=tuple(
            str(item) for item in _array(body.get("target_periods"), "target_periods")
        ),
        raw_payload_sha256=pairs("raw_payload_sha256"),
        captured_payload_bytes_sha256=pairs("captured_payload_bytes_sha256"),
        status=str(body.get("status", "")),
    )
    if _sha(_raw_capture_payload(capture)) != capture.evidence_id:
        raise ValueError("Historical raw target capture evidence hash mismatch")
    artifact_directory = str(root.get("artifact_directory", ""))
    if not artifact_directory:
        raise ValueError("Historical raw target capture artifact directory is missing")
    raw_root = Path(artifact_directory) / "raw"
    raw_hashes = dict(capture.raw_payload_sha256)
    byte_hashes = dict(capture.captured_payload_bytes_sha256)
    payloads: dict[str, object] = {}
    for period in capture.target_periods:
        raw_path = raw_root / f"{period}.json"
        if not raw_path.is_file():
            raise ValueError(f"Historical raw target capture file missing: {period}")
        raw_bytes = raw_path.read_bytes()
        if _sha_bytes(raw_bytes) != byte_hashes[period]:
            raise ValueError(f"Historical raw target capture byte hash drifted: {period}")
        payload: object = json.loads(raw_bytes.decode("utf-8"))
        if _sha(payload) != raw_hashes[period]:
            raise ValueError(f"Historical raw target capture payload hash drifted: {period}")
        payloads[period] = payload
    return capture, payloads


def run_schema_repaired_historical_evaluation_v2(
    client: OpenDartReadOnlyClient,
    *,
    evaluation_date: date,
    execution_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION_V2,
    scope_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE,
    bundle_path: str | Path = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
    estimator_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    output: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT,
) -> tuple[
    HistoricalTargetJoin,
    HistoricalBacktestResult,
    HistoricalRawTargetCapture,
    bool,
    bool,
]:
    repair = load_frozen_historical_schema_repair_v2(execution_path)
    execution = repair.runtime_execution
    scope = load_frozen_exact_twenty_period_ex_ante_scope(scope_path)
    bundle = load_point_in_time_feature_bundle(bundle_path)
    estimator = load_frozen_ex_ante_estimator_selection(estimator_path)
    root = Path(output)
    target_pointer = root / "latest_historical_target_join.json"
    target_join_reused = target_pointer.is_file()
    raw_capture_pointer = root / "latest_historical_raw_target_capture.json"

    if target_join_reused:
        join = load_historical_target_join(target_pointer)
        if join.execution_evidence_id != execution.evidence_id:
            raise ValueError("Locked historical target join belongs to another execution")
        if not raw_capture_pointer.is_file():
            raise ValueError("Locked v2 target join is missing its pre-extraction raw capture")
        capture, _raw_payloads = load_historical_raw_target_capture(raw_capture_pointer)
        raw_capture_reused = True
    else:
        raw_capture_reused = raw_capture_pointer.is_file()
        if raw_capture_reused:
            capture, raw_payloads = load_historical_raw_target_capture(raw_capture_pointer)
            if capture.execution_evidence_id != execution.evidence_id:
                raise ValueError("Historical raw target capture belongs to another execution")
            if capture.evaluation_date != evaluation_date:
                raise ValueError("Historical raw target capture evaluation date cannot drift")
        else:
            raw_payloads = collect_historical_target_payloads(client, execution)
            capture, _pointer = persist_historical_raw_target_capture(
                execution,
                evaluation_date=evaluation_date,
                raw_payloads=raw_payloads,
                output=root,
            )
        join = build_historical_target_join(
            execution,
            scope,
            bundle,
            estimator,
            evaluation_date=capture.evaluation_date,
            raw_payloads=raw_payloads,
        )
        persist_historical_target_join(join, raw_payloads, output=root)

    if capture.execution_evidence_id != execution.evidence_id:
        raise ValueError("Historical raw target capture execution evidence drifted")
    result = run_frozen_historical_backtest(execution, scope, estimator, join)
    persist_historical_backtest(result, output=root)
    return join, result, capture, raw_capture_reused, target_join_reused


__all__ = [
    "DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION_V2",
    "DEFAULT_COMPANY_GP_EX_ANTE_RAW_TARGET_CAPTURE",
    "FrozenHistoricalSchemaRepairV2",
    "HistoricalRawTargetCapture",
    "load_frozen_historical_schema_repair_v2",
    "load_historical_raw_target_capture",
    "persist_historical_raw_target_capture",
    "run_schema_repaired_historical_evaluation_v2",
]
