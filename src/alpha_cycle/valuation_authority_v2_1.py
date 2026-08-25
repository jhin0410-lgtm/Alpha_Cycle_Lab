"""Replayable valuation and scenario/payoff authority for Decision System v2.1.

This boundary deliberately separates canonical source replay from valuation eligibility.  A
legacy ``ValuationEvidenceSnapshot`` may contain useful normalized OpenDART rows, but it cannot
certify its own share counts or capital structure.  The artifact produced here therefore uses
the independently replayed live market/research snapshots for class-A actuals and records the
legacy valuation snapshot as class-B evidence only.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.live_typed_source_revalidation_v2_1 import (
    revalidate_market_snapshot,
    revalidate_research_snapshot,
)

SCHEMA_VERSION = 1
REPOSITORY_NAME = "valuation_authority_v2_1"
PARSER_ID = "alpha_cycle.valuation_authority_v2_1"
PARSER_VERSION = "1.0.0"


class ValuationAuthorityError(ValueError):
    """Raised when source bytes or a persisted authority artifact fail replay."""


class AuthorityClass(StrEnum):
    AUTHORITATIVE_SOURCE = "A_authoritative_persisted_source"
    REPLAYABLE_SEMANTICALLY_INSUFFICIENT = "B_replayable_semantically_insufficient"
    DERIVED_FROM_AUTHORITY = "C_derived_from_A"
    MODEL_ASSUMPTION = "D_model_assumption"
    UNSUPPORTED = "E_unsupported_unknown"


class ValuationMethod(StrEnum):
    TRAILING_PE = "trailing_pe"
    FORWARD_PE = "forward_pe"
    EV_EBITDA = "ev_ebitda"
    PRICE_TO_BOOK = "price_to_book"
    DCF = "dcf"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    BLOCKED = "blocked"


class ScenarioLabel(StrEnum):
    BEAR = "bear"
    BASE = "base"
    BULL = "bull"


@dataclass(frozen=True)
class ValuationInput:
    role: str
    authority_class: AuthorityClass
    source_evidence_id: str | None
    value: float | None
    unit: str | None
    currency: str | None
    period_end: date | None
    available_date: date | None
    statement_basis: str | None
    blocker: str | None = None

    def __post_init__(self) -> None:
        _text(self.role, "role")
        if self.source_evidence_id is not None:
            _sha(self.source_evidence_id, "source_evidence_id")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("valuation input value must be finite")
        if self.available_date is not None and self.period_end is None:
            raise ValueError("available_date requires period_end")
        if self.blocker is not None:
            _text(self.blocker, "blocker")

    def payload(self) -> dict[str, object]:
        return {
            "role": self.role,
            "authority_class": self.authority_class.value,
            "source_evidence_id": self.source_evidence_id,
            "value": self.value,
            "unit": self.unit,
            "currency": self.currency,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "available_date": self.available_date.isoformat() if self.available_date else None,
            "statement_basis": self.statement_basis,
            "blocker": self.blocker,
        }


@dataclass(frozen=True)
class MethodEligibility:
    method: ValuationMethod
    status: EligibilityStatus
    required_roles: tuple[str, ...]
    blockers: tuple[str, ...]
    numerator: float | None = None
    denominator: float | None = None
    derived_multiple: float | None = None

    def __post_init__(self) -> None:
        _unique_texts(self.required_roles, "required_roles")
        _unique_texts(self.blockers, "blockers")
        values = (self.numerator, self.denominator, self.derived_multiple)
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("method arithmetic must be finite")
        if self.status is EligibilityStatus.ELIGIBLE:
            if self.blockers or any(value is None for value in values):
                raise ValueError("eligible method requires complete arithmetic and no blockers")
        elif any(value is not None for value in values):
            raise ValueError("blocked method cannot expose valuation arithmetic")

    def payload(self) -> dict[str, object]:
        return {
            "method": self.method.value,
            "status": self.status.value,
            "required_roles": list(self.required_roles),
            "blockers": list(self.blockers),
            "numerator": self.numerator,
            "denominator": self.denominator,
            "derived_multiple": self.derived_multiple,
        }


@dataclass(frozen=True)
class ScenarioAuthority:
    label: ScenarioLabel
    horizon_trading_days: int
    conditions: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    model_assumption_ids: tuple[str, ...]
    valuation_method: ValuationMethod | None
    implied_value_per_share: float | None
    upside_downside: float | None
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.horizon_trading_days not in {60, 120, 250}:
            raise ValueError("scenario horizon must be 60, 120, or 250 trading days")
        _unique_texts(self.conditions, "conditions")
        _unique_shas(self.source_evidence_ids, "source_evidence_ids")
        _unique_shas(self.model_assumption_ids, "model_assumption_ids")
        _unique_texts(self.blockers, "blockers")
        if not self.conditions:
            raise ValueError("scenario conditions are required")
        if self.implied_value_per_share is None:
            if self.upside_downside is not None or not self.blockers:
                raise ValueError("unavailable scenario value requires blockers")
        else:
            if self.valuation_method is None or self.blockers:
                raise ValueError("scenario value requires an eligible method")
            if not math.isfinite(self.implied_value_per_share) or self.implied_value_per_share <= 0:
                raise ValueError("scenario value must be positive and finite")
            if self.upside_downside is None or not math.isfinite(self.upside_downside):
                raise ValueError("available scenario value requires finite upside/downside")

    def payload(self) -> dict[str, object]:
        return {
            "label": self.label.value,
            "horizon_trading_days": self.horizon_trading_days,
            "conditions": list(self.conditions),
            "source_evidence_ids": list(self.source_evidence_ids),
            "model_assumption_ids": list(self.model_assumption_ids),
            "valuation_method": self.valuation_method.value if self.valuation_method else None,
            "implied_value_per_share": self.implied_value_per_share,
            "upside_downside": self.upside_downside,
            "blockers": list(self.blockers),
            "probability": None,
            "target_price_claimed": False,
        }


@dataclass(frozen=True)
class ValuationAuthorityArtifact:
    captured_at: datetime
    evaluation_date: date
    security_id: str
    market_snapshot_id: str
    research_snapshot_id: str
    legacy_valuation_snapshot_id: str | None
    legacy_valuation_content_id: str | None
    inputs: tuple[ValuationInput, ...]
    methods: tuple[MethodEligibility, ...]
    scenarios: tuple[ScenarioAuthority, ...]

    def __post_init__(self) -> None:
        _aware(self.captured_at, "captured_at")
        _text(self.security_id, "security_id")
        _sha(self.market_snapshot_id, "market_snapshot_id")
        _sha(self.research_snapshot_id, "research_snapshot_id")
        if self.legacy_valuation_snapshot_id is not None:
            _sha(self.legacy_valuation_snapshot_id, "legacy_valuation_snapshot_id")
        if self.legacy_valuation_content_id is not None:
            _sha(self.legacy_valuation_content_id, "legacy_valuation_content_id")
        if (self.legacy_valuation_snapshot_id is None) != (
            self.legacy_valuation_content_id is None
        ):
            raise ValueError("legacy valuation identity and content binding must coexist")
        roles = tuple(item.role for item in self.inputs)
        if roles != tuple(sorted(set(roles))):
            raise ValueError("valuation inputs must have unique sorted roles")
        method_ids = tuple(item.method.value for item in self.methods)
        expected_methods = tuple(sorted(item.value for item in ValuationMethod))
        if method_ids != expected_methods:
            raise ValueError("valuation artifact requires every method exactly once")
        labels = tuple(item.label.value for item in self.scenarios)
        if labels != ("bear", "base", "bull"):
            raise ValueError("valuation artifact requires ordered bear/base/bull scenarios")
        if any(
            item.horizon_trading_days != self.scenarios[0].horizon_trading_days
            for item in self.scenarios
        ):
            raise ValueError("scenarios must share one horizon")

    def payload_without_id(self) -> dict[str, object]:
        eligible = [
            item.method.value for item in self.methods if item.status is EligibilityStatus.ELIGIBLE
        ]
        blockers = sorted(
            {blocker for method in self.methods for blocker in method.blockers}
            | {blocker for scenario in self.scenarios for blocker in scenario.blockers}
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "parser_id": PARSER_ID,
            "parser_version": PARSER_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "security_id": self.security_id,
            "market_snapshot_id": self.market_snapshot_id,
            "research_snapshot_id": self.research_snapshot_id,
            "legacy_valuation_snapshot_id": self.legacy_valuation_snapshot_id,
            "legacy_valuation_content_id": self.legacy_valuation_content_id,
            "inputs": [item.payload() for item in self.inputs],
            "methods": [item.payload() for item in self.methods],
            "scenarios": [item.payload() for item in self.scenarios],
            "eligible_methods": eligible,
            "blockers": blockers,
            "share_count_authority_established": False,
            "capital_structure_authority_established": False,
            "forward_estimate_authority_established": False,
            "price_implied_requirement_authority_established": bool(eligible),
            "payoff_surface_authority_established": all(
                not item.blockers for item in self.scenarios
            ),
            "probabilities_available": False,
            "probability_weighted_expected_return_available": False,
            "market_consensus_authority_established": False,
            "target_price_authority_established": False,
            "decision_score_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def artifact_id(self) -> str:
        return _digest(_canonical(self.payload_without_id()))

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "artifact_id": self.artifact_id}


def build_valuation_authority(
    *,
    market_directory: str | Path,
    research_directory: str | Path,
    security_id: str,
    captured_at: datetime,
    legacy_valuation_directory: str | Path | None = None,
    horizon_trading_days: int = 250,
) -> ValuationAuthorityArtifact:
    """Replay canonical upstream sources and derive honest fail-closed eligibility."""

    _aware(captured_at, "captured_at")
    market = revalidate_market_snapshot(market_directory)
    research = revalidate_research_snapshot(research_directory)
    if research.market_snapshot_id != market.snapshot_id:
        raise ValuationAuthorityError("research/market source generation mismatch")
    if captured_at < max(market.captured_at, research.captured_at):
        raise ValuationAuthorityError("authority capture cannot precede source captures")
    if captured_at.astimezone(UTC).date() < research.evaluation_date:
        raise ValuationAuthorityError("authority capture cannot precede evaluation date")

    prices = [item for item in market.prices if item.symbol == security_id]
    if len(prices) != 1:
        raise ValuationAuthorityError("security requires exactly one trusted market price")
    price = prices[0]
    if price.timestamp > captured_at:
        raise ValuationAuthorityError("market price cannot follow authority capture")

    legacy_id, legacy_content_id = _legacy_binding(
        legacy_valuation_directory,
        market_snapshot_id=market.snapshot_id,
        research_snapshot_id=research.snapshot_id,
        evaluation_date=research.evaluation_date,
        security_id=security_id,
    )
    actuals = _trusted_actual_inputs(research.financials, security_id, research.snapshot_id)
    inputs = tuple(
        sorted(
            (
                ValuationInput(
                    role="current_price",
                    authority_class=AuthorityClass.AUTHORITATIVE_SOURCE,
                    source_evidence_id=market.snapshot_id,
                    value=float(price.last_price),
                    unit="KRW/share",
                    currency=price.currency,
                    period_end=price.timestamp.date(),
                    available_date=price.timestamp.date(),
                    statement_basis="market_observation",
                ),
                *actuals,
                ValuationInput(
                    role="share_count",
                    authority_class=(
                        AuthorityClass.REPLAYABLE_SEMANTICALLY_INSUFFICIENT
                        if legacy_id
                        else AuthorityClass.UNSUPPORTED
                    ),
                    source_evidence_id=legacy_content_id,
                    value=None,
                    unit="shares",
                    currency=None,
                    period_end=None,
                    available_date=None,
                    statement_basis=None,
                    blocker="valuation_share_count_authority_missing",
                ),
                ValuationInput(
                    role="complete_debt",
                    authority_class=AuthorityClass.UNSUPPORTED,
                    source_evidence_id=research.snapshot_id,
                    value=None,
                    unit="KRW",
                    currency="KRW",
                    period_end=None,
                    available_date=None,
                    statement_basis="CFS coverage not independently certified",
                    blocker="valuation_capital_structure_authority_missing",
                ),
                ValuationInput(
                    role="forward_eps",
                    authority_class=AuthorityClass.UNSUPPORTED,
                    source_evidence_id=None,
                    value=None,
                    unit="KRW/share",
                    currency="KRW",
                    period_end=None,
                    available_date=None,
                    statement_basis=None,
                    blocker="forward_estimate_authority_missing",
                ),
                ValuationInput(
                    role="forecast_and_wacc_assumptions",
                    authority_class=AuthorityClass.UNSUPPORTED,
                    source_evidence_id=None,
                    value=None,
                    unit=None,
                    currency=None,
                    period_end=None,
                    available_date=None,
                    statement_basis=None,
                    blocker="valuation_method_ineligible",
                ),
            ),
            key=lambda item: item.role,
        )
    )
    methods = _blocked_methods()
    scenario_blockers = ("scenario_input_authority_missing", "valuation_method_ineligible")
    scenarios = tuple(
        ScenarioAuthority(
            label=label,
            horizon_trading_days=horizon_trading_days,
            conditions=(
                f"{label.value} conditional operating and valuation assumptions unavailable",
            ),
            source_evidence_ids=(market.snapshot_id, research.snapshot_id),
            model_assumption_ids=(),
            valuation_method=None,
            implied_value_per_share=None,
            upside_downside=None,
            blockers=scenario_blockers,
        )
        for label in ScenarioLabel
    )
    return ValuationAuthorityArtifact(
        captured_at=captured_at,
        evaluation_date=research.evaluation_date,
        security_id=security_id,
        market_snapshot_id=market.snapshot_id,
        research_snapshot_id=research.snapshot_id,
        legacy_valuation_snapshot_id=legacy_id,
        legacy_valuation_content_id=legacy_content_id,
        inputs=inputs,
        methods=methods,
        scenarios=scenarios,
    )


def persist_valuation_authority(
    artifact: ValuationAuthorityArtifact,
    *,
    output_root: str | Path,
) -> Path:
    root = _plain_repository(Path(output_root), create=True)
    timestamp = artifact.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{artifact.artifact_id[:12]}"
    if directory.exists() or directory.is_symlink():
        replayed = replay_persisted_valuation_authority(
            directory, expected_artifact_id=artifact.artifact_id
        )
        if replayed != artifact:
            raise ValuationAuthorityError("duplicate immutable identity conflicts with content")
        return directory
    temporary = Path(tempfile.mkdtemp(prefix=f".{directory.name}.", dir=root))
    try:
        payload_bytes = (
            json.dumps(artifact.payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": artifact.artifact_id,
            "captured_at": artifact.captured_at.isoformat(),
            "evaluation_date": artifact.evaluation_date.isoformat(),
            "security_id": artifact.security_id,
            "files": {"authority.json": _digest(payload_bytes)},
        }
        _write_new(temporary / "authority.json", payload_bytes)
        _write_new(
            temporary / "manifest.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        )
        os.rename(temporary, directory)
    finally:
        if temporary.exists():
            for child in temporary.iterdir():
                child.unlink()
            temporary.rmdir()
    return directory


def replay_persisted_valuation_authority(
    directory: str | Path,
    *,
    expected_artifact_id: str | None = None,
) -> ValuationAuthorityArtifact:
    root = _plain_directory(Path(directory))
    manifest_bytes = _read_plain(root / "manifest.json", root)
    authority_bytes = _read_plain(root / "authority.json", root)
    manifest = _object(json.loads(manifest_bytes), "manifest")
    _exact(
        manifest,
        {"schema_version", "artifact_id", "captured_at", "evaluation_date", "security_id", "files"},
        "manifest",
    )
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValuationAuthorityError("unsupported valuation authority schema")
    files = _object(manifest.get("files"), "files")
    if files != {"authority.json": _digest(authority_bytes)}:
        raise ValuationAuthorityError("authority file digest mismatch")
    payload = _object(json.loads(authority_bytes), "authority")
    artifact = _artifact_from_payload(payload)
    declared = str(manifest.get("artifact_id", ""))
    if artifact.artifact_id != declared or payload.get("artifact_id") != declared:
        raise ValuationAuthorityError("authority canonical identity mismatch")
    if expected_artifact_id is not None and declared != expected_artifact_id:
        raise ValuationAuthorityError("unexpected valuation authority identity")
    expected_name = (
        f"{artifact.captured_at.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')}__{declared[:12]}"
    )
    if root.name != expected_name:
        raise ValuationAuthorityError("authority directory identity mismatch")
    return artifact


def revalidate_persisted_valuation_authority(
    directory: str | Path,
    *,
    market_directory: str | Path,
    research_directory: str | Path,
    legacy_valuation_directory: str | Path | None,
    expected_artifact_id: str | None = None,
) -> ValuationAuthorityArtifact:
    """Rebuild an authority artifact from its upstream bytes and require exact equality."""

    persisted = replay_persisted_valuation_authority(
        directory,
        expected_artifact_id=expected_artifact_id,
    )
    rebuilt = build_valuation_authority(
        market_directory=market_directory,
        research_directory=research_directory,
        legacy_valuation_directory=legacy_valuation_directory,
        security_id=persisted.security_id,
        captured_at=persisted.captured_at,
        horizon_trading_days=persisted.scenarios[0].horizon_trading_days,
    )
    if rebuilt != persisted:
        raise ValuationAuthorityError("persisted authority differs from upstream replay")
    return persisted


def _trusted_actual_inputs(
    frame: pd.DataFrame, security_id: str, source_id: str
) -> tuple[ValuationInput, ...]:
    specs = {
        "trailing_net_income": r"^(?:CIS|IS):ifrs-full_ProfitLoss#",
        "book_equity": r"^BS:ifrs-full_Equity#",
        "cash_and_cash_equivalents": r"^BS:ifrs-full_CashAndCashEquivalents#",
    }
    company = frame.loc[frame["ticker"].astype(str).eq(security_id)].copy()
    result: list[ValuationInput] = []
    for role, pattern in specs.items():
        candidates = company.loc[company["metric"].astype(str).str.match(pattern)].copy()
        candidates = candidates.loc[candidates["fiscal_period"].astype(str).eq("FY")]
        if candidates.empty:
            result.append(
                ValuationInput(
                    role,
                    AuthorityClass.UNSUPPORTED,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "CFS",
                    f"{role}_authority_missing",
                )
            )
            continue
        latest_end = candidates["period_end"].astype(str).max()
        latest = candidates.loc[candidates["period_end"].astype(str).eq(latest_end)]
        values = pd.to_numeric(latest["value"], errors="raise").unique()
        if len(values) != 1:
            result.append(
                ValuationInput(
                    role,
                    AuthorityClass.UNSUPPORTED,
                    source_id,
                    None,
                    "KRW",
                    "KRW",
                    None,
                    None,
                    "CFS",
                    f"{role}_ambiguous",
                )
            )
            continue
        row = latest.sort_values("metric", kind="stable").iloc[0]
        result.append(
            ValuationInput(
                role=role,
                authority_class=AuthorityClass.AUTHORITATIVE_SOURCE,
                source_evidence_id=source_id,
                value=float(values[0]),
                unit=str(row["unit"]),
                currency=str(row["currency"]),
                period_end=date.fromisoformat(str(row["period_end"])),
                available_date=date.fromisoformat(str(row["available_date"])),
                statement_basis="CFS official actual",
            )
        )
    return tuple(result)


def _legacy_binding(
    directory: str | Path | None,
    *,
    market_snapshot_id: str,
    research_snapshot_id: str,
    evaluation_date: date,
    security_id: str,
) -> tuple[str | None, str | None]:
    if directory is None:
        return None, None
    root = _plain_directory(Path(directory))
    manifest = _object(
        json.loads(_read_plain(root / "manifest.json", root)), "legacy valuation manifest"
    )
    required = {
        "snapshot_id",
        "captured_at",
        "evaluation_date",
        "research_snapshot_id",
        "market_snapshot_id",
        "files",
        "symbols",
    }
    if not required.issubset(manifest):
        raise ValuationAuthorityError("legacy valuation manifest is incomplete")
    snapshot_id = str(manifest["snapshot_id"])
    _sha(snapshot_id, "legacy valuation snapshot_id")
    if (
        manifest["market_snapshot_id"] != market_snapshot_id
        or manifest["research_snapshot_id"] != research_snapshot_id
    ):
        raise ValuationAuthorityError("legacy valuation source generation mismatch")
    if manifest["evaluation_date"] != evaluation_date.isoformat():
        raise ValuationAuthorityError("legacy valuation evaluation date mismatch")
    symbols = manifest["symbols"]
    if not isinstance(symbols, list) or security_id not in symbols:
        raise ValuationAuthorityError("legacy valuation does not contain security")
    declared = manifest["files"]
    if not isinstance(declared, list):
        raise ValuationAuthorityError("legacy valuation file list is invalid")
    bindings: list[dict[str, object]] = []
    for name in sorted(declared):
        if not isinstance(name, str) or Path(name).name != name:
            raise ValuationAuthorityError("legacy valuation file name is unsafe")
        content = _read_plain(root / name, root)
        bindings.append({"name": name, "size_bytes": len(content), "sha256": _digest(content)})
    manifest_bytes = _read_plain(root / "manifest.json", root)
    binding_id = _digest(
        _canonical(
            {
                "manifest_sha256": _digest(manifest_bytes),
                "files": bindings,
            }
        )
    )
    return snapshot_id, binding_id


def _blocked_methods() -> tuple[MethodEligibility, ...]:
    rows = (
        (ValuationMethod.DCF, ("forecast_and_wacc_assumptions",), ("valuation_method_ineligible",)),
        (
            ValuationMethod.EV_EBITDA,
            (
                "current_price",
                "share_count",
                "complete_debt",
                "cash_and_cash_equivalents",
                "trailing_ebitda",
            ),
            (
                "valuation_share_count_authority_missing",
                "valuation_capital_structure_authority_missing",
                "trailing_ebitda_authority_missing",
            ),
        ),
        (
            ValuationMethod.FORWARD_PE,
            ("current_price", "forward_eps"),
            ("forward_estimate_authority_missing",),
        ),
        (
            ValuationMethod.PRICE_TO_BOOK,
            ("current_price", "share_count", "book_equity"),
            ("valuation_share_count_authority_missing",),
        ),
        (
            ValuationMethod.TRAILING_PE,
            ("current_price", "share_count", "trailing_net_income"),
            ("valuation_share_count_authority_missing",),
        ),
    )
    return tuple(
        MethodEligibility(method, EligibilityStatus.BLOCKED, required, blockers)
        for method, required, blockers in rows
    )


def _artifact_from_payload(payload: dict[str, object]) -> ValuationAuthorityArtifact:
    expected = {
        "schema_version",
        "parser_id",
        "parser_version",
        "captured_at",
        "evaluation_date",
        "security_id",
        "market_snapshot_id",
        "research_snapshot_id",
        "legacy_valuation_snapshot_id",
        "legacy_valuation_content_id",
        "inputs",
        "methods",
        "scenarios",
        "eligible_methods",
        "blockers",
        "share_count_authority_established",
        "capital_structure_authority_established",
        "forward_estimate_authority_established",
        "price_implied_requirement_authority_established",
        "payoff_surface_authority_established",
        "probabilities_available",
        "probability_weighted_expected_return_available",
        "market_consensus_authority_established",
        "target_price_authority_established",
        "decision_score_enabled",
        "automatic_execution_enabled",
        "artifact_id",
    }
    _exact(payload, expected, "authority")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("parser_id") != PARSER_ID
        or payload.get("parser_version") != PARSER_VERSION
    ):
        raise ValuationAuthorityError("authority parser contract mismatch")
    inputs_raw = _list(payload.get("inputs"), "inputs")
    methods_raw = _list(payload.get("methods"), "methods")
    scenarios_raw = _list(payload.get("scenarios"), "scenarios")
    inputs = tuple(_input_from_payload(_object(item, "input")) for item in inputs_raw)
    methods = tuple(_method_from_payload(_object(item, "method")) for item in methods_raw)
    scenarios = tuple(_scenario_from_payload(_object(item, "scenario")) for item in scenarios_raw)
    artifact = ValuationAuthorityArtifact(
        captured_at=datetime.fromisoformat(str(payload["captured_at"])),
        evaluation_date=date.fromisoformat(str(payload["evaluation_date"])),
        security_id=str(payload["security_id"]),
        market_snapshot_id=str(payload["market_snapshot_id"]),
        research_snapshot_id=str(payload["research_snapshot_id"]),
        legacy_valuation_snapshot_id=cast(str | None, payload["legacy_valuation_snapshot_id"]),
        legacy_valuation_content_id=cast(str | None, payload["legacy_valuation_content_id"]),
        inputs=inputs,
        methods=methods,
        scenarios=scenarios,
    )
    if artifact.payload_without_id() != {
        key: value for key, value in payload.items() if key != "artifact_id"
    }:
        raise ValuationAuthorityError("authority payload is not canonical")
    return artifact


def _input_from_payload(raw: dict[str, object]) -> ValuationInput:
    _exact(
        raw,
        {
            "role",
            "authority_class",
            "source_evidence_id",
            "value",
            "unit",
            "currency",
            "period_end",
            "available_date",
            "statement_basis",
            "blocker",
        },
        "input",
    )
    return ValuationInput(
        str(raw["role"]),
        AuthorityClass(str(raw["authority_class"])),
        cast(str | None, raw["source_evidence_id"]),
        cast(float | None, raw["value"]),
        cast(str | None, raw["unit"]),
        cast(str | None, raw["currency"]),
        date.fromisoformat(str(raw["period_end"])) if raw["period_end"] else None,
        date.fromisoformat(str(raw["available_date"])) if raw["available_date"] else None,
        cast(str | None, raw["statement_basis"]),
        cast(str | None, raw["blocker"]),
    )


def _method_from_payload(raw: dict[str, object]) -> MethodEligibility:
    _exact(
        raw,
        {
            "method",
            "status",
            "required_roles",
            "blockers",
            "numerator",
            "denominator",
            "derived_multiple",
        },
        "method",
    )
    return MethodEligibility(
        ValuationMethod(str(raw["method"])),
        EligibilityStatus(str(raw["status"])),
        tuple(str(item) for item in _list(raw["required_roles"], "required_roles")),
        tuple(str(item) for item in _list(raw["blockers"], "blockers")),
        cast(float | None, raw["numerator"]),
        cast(float | None, raw["denominator"]),
        cast(float | None, raw["derived_multiple"]),
    )


def _scenario_from_payload(raw: dict[str, object]) -> ScenarioAuthority:
    _exact(
        raw,
        {
            "label",
            "horizon_trading_days",
            "conditions",
            "source_evidence_ids",
            "model_assumption_ids",
            "valuation_method",
            "implied_value_per_share",
            "upside_downside",
            "blockers",
            "probability",
            "target_price_claimed",
        },
        "scenario",
    )
    if raw["probability"] is not None or raw["target_price_claimed"] is not False:
        raise ValuationAuthorityError("unsupported scenario authority claim")
    method = ValuationMethod(str(raw["valuation_method"])) if raw["valuation_method"] else None
    return ScenarioAuthority(
        ScenarioLabel(str(raw["label"])),
        int(cast(int, raw["horizon_trading_days"])),
        tuple(str(item) for item in _list(raw["conditions"], "conditions")),
        tuple(str(item) for item in _list(raw["source_evidence_ids"], "source_evidence_ids")),
        tuple(str(item) for item in _list(raw["model_assumption_ids"], "model_assumption_ids")),
        method,
        cast(float | None, raw["implied_value_per_share"]),
        cast(float | None, raw["upside_downside"]),
        tuple(str(item) for item in _list(raw["blockers"], "blockers")),
    )


def _plain_repository(path: Path, *, create: bool) -> Path:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_dir():
            raise ValuationAuthorityError("authority repository must be a plain directory")
    elif create:
        path.mkdir(parents=True)
    return path.resolve()


def _plain_directory(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValuationAuthorityError("snapshot must be a plain directory")
    resolved = path.resolve()
    if resolved != path.absolute():
        raise ValuationAuthorityError("snapshot path contains a junction or alias")
    return resolved


def _read_plain(path: Path, directory: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.resolve().parent != directory:
        raise ValuationAuthorityError("source file escapes snapshot directory")
    return path.read_bytes()


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _unique_texts(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _text(value, field)
    if len(values) != len(set(values)):
        raise ValueError(f"{field} cannot contain duplicates")


def _unique_shas(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _sha(value, field)
    if len(values) != len(set(values)):
        raise ValueError(f"{field} cannot contain duplicates")


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValuationAuthorityError(f"{field} must be an object")
    return {str(key): item for key, item in value.items()}


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValuationAuthorityError(f"{field} must be an array")
    return value


def _exact(value: dict[str, object], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise ValuationAuthorityError(f"{field} fields differ from canonical schema")


__all__ = [
    "AuthorityClass",
    "EligibilityStatus",
    "MethodEligibility",
    "ScenarioAuthority",
    "ScenarioLabel",
    "ValuationAuthorityArtifact",
    "ValuationAuthorityError",
    "ValuationInput",
    "ValuationMethod",
    "build_valuation_authority",
    "persist_valuation_authority",
    "revalidate_persisted_valuation_authority",
    "replay_persisted_valuation_authority",
]
