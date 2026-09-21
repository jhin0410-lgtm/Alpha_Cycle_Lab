"""Adapt replayed OpenDART current-term fields to the shared R1 universe.

The adapter reconstructs selected rows from raw responses using the existing
valuation source validator. It preserves acquisition time, exact account and
report scope. Byte replay and raw-row agreement do not certify remote origin,
historical vintages, forward estimates, or independent decision authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from alpha_cycle.intelligence.observable_universe import (
    EvidenceMaturity,
    EvidenceReference,
    MeasuredObservation,
    MemberKind,
    ObservableUniverseSnapshot,
    UniverseMember,
)
from alpha_cycle.live_typed_source_revalidation_v2_1 import revalidate_research_snapshot
from alpha_cycle.valuation_authority_v2_1 import (
    _opendart_statement_basis,
    _require_raw_actual_binding,
)


@dataclass(frozen=True)
class OpenDartFieldSelection:
    security_id: str
    domain_id: str
    dimension_id: str
    metric_id: str
    period_end: date
    fiscal_period: str
    statement_basis: str = "CFS"

    def __post_init__(self) -> None:
        if len(self.security_id) != 6 or not self.security_id.isdigit():
            raise ValueError("OpenDART security must be a six-digit stock code")
        if any(not value.strip() for value in (
            self.domain_id, self.dimension_id, self.metric_id, self.fiscal_period
        )):
            raise ValueError("field selection requires exact non-empty semantics")
        if self.statement_basis not in {"CFS", "OFS"}:
            raise ValueError("unsupported OpenDART statement basis")


def load_opendart_universe(
    research_directory: str | Path,
    *,
    selections: tuple[OpenDartFieldSelection, ...],
    universe_id: str,
    version: str,
    cutoff_at: datetime,
) -> ObservableUniverseSnapshot:
    """Replay a writer artifact and select exact raw-bound current-term fields.

    Selection must be unambiguous. ``thstrm_amount`` is kept in the window and
    semantic label: a half-year filing does not make this field a six-month sum.
    The earliest allowed cutoff is capture time, even for an older filing.
    """
    if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("research cutoff must be timezone-aware")
    if not selections:
        raise ValueError("at least one field selection is required")
    if len({(s.security_id, s.dimension_id) for s in selections}) != len(selections):
        raise ValueError("duplicate security/dimension selection")
    source = revalidate_research_snapshot(research_directory)
    if source.captured_at > cutoff_at:
        raise ValueError("source capture exceeds research cutoff")
    observations: list[MeasuredObservation] = []
    domains: dict[str, str] = {}
    dimensions: dict[str, list[str]] = {}
    for selection in selections:
        if domains.setdefault(selection.security_id, selection.domain_id) != selection.domain_id:
            raise ValueError("one security cannot have conflicting domain mappings")
        if _opendart_statement_basis(source.raw_opendart, selection.security_id) != (
            selection.statement_basis
        ):
            raise ValueError("selected statement basis differs from raw OpenDART request")
        rows = source.financials.loc[
            source.financials["ticker"].astype(str).eq(selection.security_id)
            & source.financials["metric"].astype(str).eq(selection.metric_id)
            & source.financials["period_end"].astype(str).eq(selection.period_end.isoformat())
            & source.financials["fiscal_period"].astype(str).eq(selection.fiscal_period)
            & source.financials["source"].astype(str).eq("opendart")
        ]
        if len(rows) != 1:
            raise ValueError("field selection must identify exactly one source row")
        row = rows.iloc[0]
        _require_raw_actual_binding(source.raw_opendart, selection.security_id, row)
        amount = Decimal(str(row["value"]))
        if not amount.is_finite() or amount != amount.to_integral_value():
            raise ValueError("current-term KRW amount must be an exact integer")
        # Capture is the conservative vintage-availability boundary. Do not
        # backdate the observation to receipt date from a current API response.
        available = max(
            source.captured_at,
            datetime.fromisoformat(str(row["retrieved_at"])),
            datetime.combine(
                date.fromisoformat(str(row["available_date"])), datetime.min.time(), UTC
            ),
        )
        scope = {
            "snapshot_id": source.snapshot_id,
            "security_id": selection.security_id,
            "metric_id": selection.metric_id,
            "period_end": selection.period_end.isoformat(),
            "fiscal_period": selection.fiscal_period,
            "statement_basis": selection.statement_basis,
            "raw_field": "thstrm_amount",
            "receipt": str(row["revision_id"]),
            "value": str(amount),
            "available_at": available.isoformat(),
        }
        reference_id = hashlib.sha256(
            json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        maturity = EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE
        reference = EvidenceReference(
            reference_id, "opendart", available, maturity,
            "raw_reconstructed_reported_current_term_field",
        )
        observations.append(MeasuredObservation(
            member_id=selection.security_id,
            dimension_id=selection.dimension_id,
            metric_id=selection.metric_id,
            value=int(amount),
            unit="KRW",
            basis=selection.statement_basis,
            window=f"{selection.fiscal_period}:{selection.period_end}:thstrm_amount",
            semantics="reported_current_term_field_not_annualized_or_cumulative",
            observed_at=datetime.combine(selection.period_end, datetime.min.time(), UTC),
            available_at=available,
            maturity=maturity,
            evidence=(reference,),
        ))
        dimensions.setdefault(selection.security_id, []).append(selection.dimension_id)
    members = tuple(
        UniverseMember(
            member_id=security_id,
            kind=MemberKind.SECURITY,
            domain_id=domains[security_id],
            required_dimensions=tuple(values),
            available_dimensions=tuple(values),
        )
        for security_id, values in sorted(dimensions.items())
    )
    return ObservableUniverseSnapshot(
        universe_id=universe_id,
        version=version,
        research_cutoff_at=cutoff_at,
        members=members,
        observations=tuple(observations),
        source_evidence_refs=tuple(
            ref.reference_id for item in observations for ref in item.evidence
        ),
    )
