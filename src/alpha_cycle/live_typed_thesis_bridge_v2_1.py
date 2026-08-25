"""Source-backed thesis production for the live Decision System v2.1 bridge.

This bridge promotes only directly observed facts from the frozen market and official
fundamental/macro snapshots. It deliberately stops at ``EVIDENCE_GATED`` and never infers
consensus, valuation authority, investability, target price, or position size.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from alpha_cycle.intelligence.decision_thesis_v2 import (
    ClaimDirection,
    EpistemicStatus,
    InvestmentThesisSnapshot,
    ThesisClaim,
    ThesisStatus,
    ThesisUncertainty,
    UncertaintyDimension,
    UncertaintyLevel,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundBlocker
from alpha_cycle.investment_thesis_repository_v2_1 import (
    load_investment_thesis,
    persist_investment_thesis,
)
from alpha_cycle.live_typed_source_manifest_v2_1 import (
    FrozenSourceSnapshot,
    LiveTypedSourceManifest,
    verify_live_typed_source_manifest,
)
from alpha_cycle.live_typed_source_revalidation_v2_1 import (
    revalidate_market_snapshot,
    revalidate_research_snapshot,
)
from alpha_cycle.providers.tossinvest import MarketPrice

_PREFERRED_FINANCIAL_METRICS = (
    "revenue",
    "operating_income",
    "net_income",
    "equity",
    "assets",
)


@dataclass(frozen=True)
class LiveTypedThesisProductionReceipt:
    source_manifest_id: str
    theses: tuple[InvestmentThesisSnapshot, ...]
    thesis_paths: tuple[Path, ...]
    blockers: tuple[ResearchRoundBlocker, ...]

    def payload(self) -> dict[str, object]:
        return {
            "source_manifest_id": self.source_manifest_id,
            "thesis_snapshot_ids": [item.snapshot_id for item in self.theses],
            "thesis_paths": [str(item) for item in self.thesis_paths],
            "blockers": [item.payload() for item in self.blockers],
            "investment_conclusion_created": False,
            "target_price_enabled": False,
            "optimal_position_size_enabled": False,
            "automatic_execution_enabled": False,
        }


def produce_source_backed_theses(
    manifest: LiveTypedSourceManifest,
    *,
    artifact_root: str | Path,
    security_ids: tuple[str, ...],
    horizon_trading_days: int,
    captured_at: datetime,
) -> LiveTypedThesisProductionReceipt:
    """Create only factual, evidence-gated theses from frozen market and official facts."""

    _require_aware(captured_at, "captured_at")
    if captured_at < manifest.frozen_at:
        raise ValueError("thesis captured_at cannot precede source-manifest freeze")
    if captured_at > manifest.research_cutoff_at:
        raise ValueError("thesis captured_at cannot follow research_cutoff_at")
    canonical_security_ids = _canonical_security_ids(security_ids)
    root = Path(artifact_root)
    verify_live_typed_source_manifest(manifest, artifact_root=root)

    market_source = _required_source(manifest, "market")
    research_source = _required_source(manifest, "research")
    market_directory = root.resolve() / market_source.snapshot_path
    research_directory = root.resolve() / research_source.snapshot_path
    canonical_market = revalidate_market_snapshot(market_directory)
    canonical_research = revalidate_research_snapshot(research_directory)
    if canonical_market.snapshot_id != market_source.snapshot_id:
        raise ValueError("frozen market source differs from canonical reconstructed identity")
    if canonical_research.snapshot_id != research_source.snapshot_id:
        raise ValueError("frozen research source differs from canonical reconstructed identity")
    if canonical_research.evaluation_date != manifest.evaluation_date:
        raise ValueError("canonical research evaluation_date differs from source manifest")
    if canonical_research.market_snapshot_id != canonical_market.snapshot_id:
        raise ValueError("mixed source generations: research market binding mismatch")

    market_rows = canonical_market.prices
    financial_rows = tuple(
        {str(key): value for key, value in row.items()}
        for row in canonical_research.financials.to_dict(orient="records")
    )

    theses: list[InvestmentThesisSnapshot] = []
    paths: list[Path] = []
    blockers: list[ResearchRoundBlocker] = []
    for security_id in canonical_security_ids:
        market_row = _market_row(market_rows, security_id)
        security_financials = tuple(
            row for row in financial_rows if str(row["ticker"]) == security_id
        )
        if market_row is None:
            blockers.append(
                _blocker(
                    "market_source",
                    "live_market_observation_missing",
                    security_id,
                )
            )
            continue
        if not security_financials:
            blockers.append(
                _blocker(
                    "official_financial_source",
                    "live_official_financial_fact_missing",
                    security_id,
                )
            )
            continue

        _validate_market_row_pit(market_row, canonical_market.captured_at)
        latest_period, selected_financials = _latest_financial_facts(
            security_financials,
            evaluation_date=manifest.evaluation_date,
        )
        if not selected_financials:
            blockers.append(
                _blocker(
                    "official_financial_source",
                    "live_official_financial_fact_not_visible_at_evaluation_date",
                    security_id,
                )
            )
            continue

        thesis = _build_thesis(
            manifest,
            market_source=market_source,
            research_source=research_source,
            market_row=market_row,
            financial_rows=selected_financials,
            security_id=security_id,
            latest_period=latest_period,
            horizon_trading_days=horizon_trading_days,
            captured_at=captured_at,
        )
        path = root / "investment_thesis_v2_1" / f"{thesis.snapshot_id}.json"
        if path.exists():
            if load_investment_thesis(path) != thesis:
                raise ValueError("existing investment thesis conflicts with canonical replay")
        else:
            path = persist_investment_thesis(thesis, artifact_root=root)
        theses.append(thesis)
        paths.append(path)

    return LiveTypedThesisProductionReceipt(
        source_manifest_id=manifest.manifest_id,
        theses=tuple(theses),
        thesis_paths=tuple(paths),
        blockers=tuple(blockers),
    )


def _build_thesis(
    manifest: LiveTypedSourceManifest,
    *,
    market_source: FrozenSourceSnapshot,
    research_source: FrozenSourceSnapshot,
    market_row: MarketPrice,
    financial_rows: tuple[dict[str, object], ...],
    security_id: str,
    latest_period: date,
    horizon_trading_days: int,
    captured_at: datetime,
) -> InvestmentThesisSnapshot:
    last_price = str(market_row.last_price)
    currency = market_row.currency
    price_timestamp = market_row.timestamp.isoformat()
    claims: list[ThesisClaim] = [
        ThesisClaim(
            claim_id="frozen_market_price",
            category="market_state",
            statement=(
                f"{security_id} frozen market observation at {price_timestamp}: "
                f"last_price={last_price} {currency}."
            ),
            epistemic_status=EpistemicStatus.OBSERVED_FACT,
            direction=ClaimDirection.NEUTRAL,
            evidence_refs=(market_source.snapshot_id,),
        )
    ]
    for row in financial_rows:
        metric = str(row["metric"])
        value = str(row["value"])
        unit = str(row["unit"])
        available_date = _as_date(row["available_date"], "available_date").isoformat()
        claims.append(
            ThesisClaim(
                claim_id=f"official_financial_{metric}",
                category="official_financial_fact",
                statement=(
                    f"{security_id} official PIT financial fact for {latest_period.isoformat()}: "
                    f"{metric}={value} {unit}, available_date={available_date}."
                ),
                epistemic_status=EpistemicStatus.OBSERVED_FACT,
                direction=ClaimDirection.NEUTRAL,
                evidence_refs=(research_source.snapshot_id,),
            )
        )

    uncertainty = ThesisUncertainty(
        evidence=UncertaintyDimension(
            level=UncertaintyLevel.MEDIUM,
            rationale=(
                "Market and official financial facts are frozen, but this bridge does not claim "
                "that all economically material evidence has been collected."
            ),
        ),
        model=UncertaintyDimension(
            level=UncertaintyLevel.UNKNOWN,
            rationale="No directional earnings or valuation model is promoted by this bridge.",
        ),
        regime=UncertaintyDimension(
            level=UncertaintyLevel.UNKNOWN,
            rationale="No validated regime classification is inferred from source selection alone.",
        ),
        expectation=UncertaintyDimension(
            level=UncertaintyLevel.UNKNOWN,
            rationale="No provider-authoritative market consensus is established here.",
        ),
        catalyst=UncertaintyDimension(
            level=UncertaintyLevel.UNKNOWN,
            rationale="No evidence-backed catalyst clock is constructed from these two sources.",
        ),
        valuation=UncertaintyDimension(
            level=UncertaintyLevel.UNKNOWN,
            rationale="No independently revalidated valuation authority is established here.",
        ),
    )
    return InvestmentThesisSnapshot(
        thesis_id=f"live-typed:{manifest.manifest_id}:{security_id}:{horizon_trading_days}",
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=captured_at,
        security_id=security_id,
        horizon_trading_days=horizon_trading_days,
        variant_view=(
            f"Frozen PIT facts show {security_id} at {last_price} {currency} with latest visible "
            f"official financial period {latest_period.isoformat()}; directional inference remains "
            "evidence-gated."
        ),
        why_now=(
            f"Source manifest {manifest.manifest_id[:12]} freezes market snapshot "
            f"{market_source.snapshot_id[:12]} and official research snapshot "
            f"{research_source.snapshot_id[:12]} before the research cutoff."
        ),
        claims=tuple(claims),
        catalysts=(),
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=uncertainty,
        kill_conditions=(),
        first_rejection_risk=(
            "No provider-authoritative expectation or independently revalidated valuation is "
            "bound by this source-only thesis bridge."
        ),
        portfolio_overlap=(),
        opportunity_set_refs=(),
        status=ThesisStatus.EVIDENCE_GATED,
    )


def _latest_financial_facts(
    rows: tuple[dict[str, object], ...],
    *,
    evaluation_date: date,
) -> tuple[date, tuple[dict[str, object], ...]]:
    visible: list[tuple[date, dict[str, object]]] = []
    for row in rows:
        period_end = _as_date(row["period_end"], "period_end")
        available_date = _as_date(row["available_date"], "available_date")
        if period_end <= evaluation_date and available_date <= evaluation_date:
            visible.append((period_end, row))
    if not visible:
        return evaluation_date, ()
    latest_period = max(item[0] for item in visible)
    latest_rows = tuple(row for period, row in visible if period == latest_period)
    by_metric = {str(row["metric"]): row for row in latest_rows}
    preferred = tuple(
        by_metric[metric] for metric in _PREFERRED_FINANCIAL_METRICS if metric in by_metric
    )
    if preferred:
        return latest_period, preferred
    fallback_metrics = sorted(by_metric)[:3]
    return latest_period, tuple(by_metric[metric] for metric in fallback_metrics)


def _market_row(rows: tuple[MarketPrice, ...], security_id: str) -> MarketPrice | None:
    matches = tuple(row for row in rows if row.symbol == security_id)
    if len(matches) > 1:
        raise ValueError(f"multiple frozen market price rows found for {security_id}")
    return matches[0] if matches else None


def _validate_market_row_pit(row: MarketPrice, captured_at: datetime) -> None:
    _require_aware(row.timestamp, "market timestamp")
    if row.timestamp > captured_at:
        raise ValueError("market observation cannot follow market source captured_at")


def _required_source(
    manifest: LiveTypedSourceManifest,
    role: str,
) -> FrozenSourceSnapshot:
    matches = tuple(source for source in manifest.sources if source.role == role)
    if len(matches) != 1:
        raise ValueError(f"source manifest requires exactly one {role!r} source")
    return matches[0]


def _canonical_security_ids(security_ids: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(item.strip() for item in security_ids)
    if not normalized or any(not item for item in normalized):
        raise ValueError("security_ids must contain non-empty identifiers")
    if len(set(normalized)) != len(normalized):
        raise ValueError("security_ids cannot contain duplicates")
    return normalized


def _blocker(component: str, code: str, security_id: str) -> ResearchRoundBlocker:
    return ResearchRoundBlocker(
        component=component,
        code=code,
        detail=code.replace("_", " "),
        security_id=security_id,
    )


def _as_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date") from exc
    raise ValueError(f"{field} must be a canonical date")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


__all__ = ["LiveTypedThesisProductionReceipt", "produce_source_backed_theses"]
