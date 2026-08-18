"""Load the frozen point-in-time feature frontier for SK hynix ex-ante GP research."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER = Path(
    "config/skhynix_company_gp_ex_ante_feature_frontier.v1.yaml"
)
_ALLOWED_PROVENANCE_CLASSES = frozenset(
    {
        "timestamped_immutable_filing",
        "historical_version_archive",
        "prospective_snapshot",
        "current_retrieval_only",
    }
)
_REQUIRED_FORBIDDEN_FEATURES = frozenset(
    {
        "current_quarter_company_gross_profit_actual",
        "current_quarter_company_revenue_actual_from_earnings_release",
        "current_quarter_product_revenue_actual_from_earnings_release",
        "current_quarter_dram_asp_actual_direction_from_earnings_release",
        "current_quarter_dram_bit_volume_actual_direction_from_earnings_release",
        "current_quarter_nand_asp_actual_direction_from_earnings_release",
        "current_quarter_nand_bit_volume_actual_direction_from_earnings_release",
        "any_value_with_available_at_after_forecast_origin",
        "any_current_retrieval_only_historical_value_from_revision_prone_series",
    }
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


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Ex-ante feature frontier {label} must be an object")
    return cast(dict[object, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"Ex-ante feature frontier {label} must be an array")
    return value


@dataclass(frozen=True)
class ExAnteFeatureSpec:
    feature_id: str
    family: str
    transform: str
    source_kind: str
    source_authority: str
    source_mutability: str
    acceptable_provenance_classes: tuple[str, ...]
    current_source_identity_status: str
    historical_pit_fit_eligible_now: bool
    prospective_capture_eligible: bool

    def __post_init__(self) -> None:
        required = (
            self.feature_id,
            self.family,
            self.transform,
            self.source_kind,
            self.source_authority,
            self.source_mutability,
            self.current_source_identity_status,
        )
        if any(not value.strip() for value in required):
            raise ValueError("Ex-ante feature spec contains blank required fields")
        if len(set(self.acceptable_provenance_classes)) != len(
            self.acceptable_provenance_classes
        ):
            raise ValueError("Ex-ante feature spec provenance classes must be unique")
        if any(
            value not in _ALLOWED_PROVENANCE_CLASSES
            for value in self.acceptable_provenance_classes
        ):
            raise ValueError("Ex-ante feature spec uses an unknown provenance class")
        if self.historical_pit_fit_eligible_now:
            raise ValueError(
                "Frozen ex-ante frontier cannot pre-claim historical PIT eligibility"
            )
        if (
            self.feature_id == "memory_price_proxy"
            and self.prospective_capture_eligible
        ):
            raise ValueError("Unresolved memory-price proxy cannot be capture-eligible")


@dataclass(frozen=True)
class ExAnteFeatureFrontier:
    evidence_id: str
    frontier_id: str
    frontier_version: str
    status: str
    ticker: str
    protocol_path: str
    features: tuple[ExAnteFeatureSpec, ...]
    forbidden_features: tuple[str, ...]
    first_pit_backtest_run: bool
    estimator_fit_allowed: bool
    q3_target_read: bool
    q3_source_outcome_loaded: bool
    numeric_forward_forecast_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64:
            raise ValueError("Ex-ante feature frontier evidence id must be SHA-256")
        if self.frontier_id != "skhynix_company_gp_ex_ante_pit_feature_frontier":
            raise ValueError("Ex-ante feature frontier id drifted")
        if (
            self.frontier_version != "1.0-frozen-pre-pit-backtest"
            or self.status != "frozen_pre_pit_backtest"
        ):
            raise ValueError("Ex-ante feature frontier is not frozen pre-PIT-backtest")
        if self.ticker != "000660":
            raise ValueError("Ex-ante feature frontier ticker drifted")
        if self.protocol_path != (
            "config/skhynix_company_gp_ex_ante_forecast_protocol.v1.yaml"
        ):
            raise ValueError("Ex-ante feature frontier protocol path drifted")
        feature_ids = tuple(item.feature_id for item in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Ex-ante feature ids must be unique")
        if "memory_price_proxy" not in feature_ids:
            raise ValueError("Ex-ante frontier must preserve unresolved price-source gap")
        if not _REQUIRED_FORBIDDEN_FEATURES.issubset(set(self.forbidden_features)):
            raise ValueError("Ex-ante feature frontier lost required leakage prohibitions")
        if any(
            (
                self.first_pit_backtest_run,
                self.estimator_fit_allowed,
                self.q3_target_read,
                self.q3_source_outcome_loaded,
                self.numeric_forward_forecast_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
            )
        ):
            raise ValueError("Ex-ante feature frontier opened prohibited scope")

    def by_id(self) -> dict[str, ExAnteFeatureSpec]:
        return {item.feature_id: item for item in self.features}


def load_ex_ante_feature_frontier(
    path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER,
) -> ExAnteFeatureFrontier:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Ex-ante feature frontier schema is invalid")
    body = _mapping(root.get("frontier"), "body")
    raw_features = _list(body.get("features"), "features")
    features: list[ExAnteFeatureSpec] = []
    for raw_feature in raw_features:
        feature = _mapping(raw_feature, "feature")
        provenance = _list(
            feature.get("acceptable_provenance_classes"),
            "acceptable_provenance_classes",
        )
        features.append(
            ExAnteFeatureSpec(
                feature_id=str(feature.get("feature_id", "")),
                family=str(feature.get("family", "")),
                transform=str(feature.get("transform", "")),
                source_kind=str(feature.get("source_kind", "")),
                source_authority=str(feature.get("source_authority", "")),
                source_mutability=str(feature.get("source_mutability", "")),
                acceptable_provenance_classes=tuple(str(item) for item in provenance),
                current_source_identity_status=str(
                    feature.get("current_source_identity_status", "")
                ),
                historical_pit_fit_eligible_now=(
                    feature.get("historical_pit_fit_eligible_now") is True
                ),
                prospective_capture_eligible=(
                    feature.get("prospective_capture_eligible") is True
                ),
            )
        )
    forbidden = _list(body.get("forbidden_features"), "forbidden_features")
    trust = _mapping(body.get("trust_boundary"), "trust_boundary")
    stable = {"schema_version": root["schema_version"], "frontier": body}
    return ExAnteFeatureFrontier(
        evidence_id=_sha(stable),
        frontier_id=str(body.get("frontier_id", "")),
        frontier_version=str(body.get("frontier_version", "")),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        protocol_path=str(body.get("protocol_path", "")),
        features=tuple(features),
        forbidden_features=tuple(str(item) for item in forbidden),
        first_pit_backtest_run=trust.get("first_pit_backtest_run") is True,
        estimator_fit_allowed=trust.get("estimator_fit_allowed") is True,
        q3_target_read=trust.get("2026q3_target_read") is True,
        q3_source_outcome_loaded=(
            trust.get("2026q3_source_outcome_loaded") is True
        ),
        numeric_forward_forecast_enabled=(
            trust.get("numeric_forward_forecast_enabled") is True
        ),
        target_price_enabled=trust.get("target_price_enabled") is True,
        decision_score_enabled=trust.get("decision_score_enabled") is True,
    )


__all__ = [
    "DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER",
    "ExAnteFeatureFrontier",
    "ExAnteFeatureSpec",
    "load_ex_ante_feature_frontier",
]
