"""Run a persisted OpenDART observation -> change -> R1 research handoff."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from alpha_cycle.intelligence.deep_research_integration_v1 import build_deep_research_package
from alpha_cycle.intelligence.knowledge_pack_repository_v1 import load_knowledge_pack_json
from alpha_cycle.intelligence.observable_universe import (
    CandidateRule,
    ChangeState,
    ConcurrentUniverseUpdateError,
    ResearchPriority,
    compare_universe_snapshots,
    load_current_universe_state,
    persist_successful_universe_attempt,
    planner_input,
    publish_failed_universe_attempt,
    surface_research_candidates,
)
from alpha_cycle.intelligence.persisted_research_plan_v1 import (
    DriverObservationBinding,
    build_persisted_research_plan,
)
from alpha_cycle.intelligence.r1_opendart_observations import (
    OpenDartFieldSelection,
    load_opendart_universe,
)
from alpha_cycle.intelligence.r1_opendart_reconciliation import (
    persist_opendart_reconciliation,
    require_reconciled_universe,
    verify_opendart_reported_fields,
)
from alpha_cycle.intelligence.r1_source_authority_v1 import build_opendart_source_authority_manifest
from alpha_cycle.intelligence.research_model_runtime_v1 import build_research_plan


def _selection(value: str) -> OpenDartFieldSelection:
    parts = value.split("|")
    if len(parts) != 6:
        raise argparse.ArgumentTypeError(
            "field must be security|domain|dimension|metric|period-end|fiscal-period"
        )
    try:
        return OpenDartFieldSelection(
            parts[0], parts[1], parts[2], parts[3], date.fromisoformat(parts[4]), parts[5]
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-source", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--universe-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--field", required=True, action="append", type=_selection)
    parser.add_argument("--pack", type=Path)
    parser.add_argument("--maximum-age-days", type=int, default=365)
    parser.add_argument("--verify-official", action="store_true")
    args = parser.parse_args(argv)
    now = datetime.now(UTC)
    previous = load_current_universe_state(args.store)
    expected_attempt = None if previous is None else previous.attempt_id
    try:
        if args.maximum_age_days < 0:
            raise ValueError("maximum age must be nonnegative")
        reconciliation: dict[str, object] | None = None
        claim_authority: dict[str, object] | None = None
        if args.verify_official:
            verified = verify_opendart_reported_fields(
                args.research_source, selections=tuple(args.field)
            )
            receipt = persist_opendart_reconciliation(verified, args.store / "reconciliations")
            reconciliation = {
                "content_id": verified.content_id,
                "artifact": str(receipt.resolve()),
                "fresh_official_verification": verified.fresh_official_verification,
                "verified_at": verified.verified_at.isoformat(),
                "claims": json.loads(verified.claims_json),
            }
            # Fresh verification must not be backdated to the original capture.
            now = datetime.now(UTC)
        current = load_opendart_universe(
            args.research_source, selections=tuple(args.field),
            universe_id=args.universe_id, version=args.version, cutoff_at=now,
        )
        if args.verify_official:
            require_reconciled_universe(verified, current)
            authority = build_opendart_source_authority_manifest(
                current, verified,
                decision_critical_reference_ids=tuple(sorted(current.source_evidence_refs)),
            )
            claim_authority = {
                "manifest_id": authority.content_id,
                "manifest": authority.payload(),
                "real_pit_evidence": authority.real_pit_evidence,
                "source_authority_established": authority.source_authority_established,
                "scope": "selected_reported_fields_only_at_current_cutoff",
            }
        pack = None if args.pack is None else load_knowledge_pack_json(
            args.pack.read_text(encoding="utf-8")
        )
        if pack is not None and any(
            member.domain_id != pack.domain_id for member in current.members
        ):
            raise ValueError("selected pack must match every selected security domain")
        # A failed latest attempt cannot silently reuse an older success.
        # A valid new acquisition recovers by establishing an explicit baseline.
        prior = None if previous is None or not previous.ready else previous.snapshot
        changes = () if prior is None else compare_universe_snapshots(prior, current)
        rules = tuple(
            CandidateRule(
                f"research:{dimension}", dimension,
                (ChangeState.CHANGED, ChangeState.NEWLY_AVAILABLE, ChangeState.INCOMPARABLE),
                ResearchPriority.ROUTINE,
                "Review changed or newly available reported field; not an investment signal",
            )
            for dimension in sorted({item.dimension_id for item in current.observations})
        )
        candidates = () if prior is None else surface_research_candidates(
            current, changes, rules, prior_snapshot=prior
        )
        persist_successful_universe_attempt(
            current, output_root=args.store, attempted_at=now,
            expected_current_attempt_id=expected_attempt,
        )
        published = load_current_universe_state(args.store)
        if published is None or published.snapshot != current:
            raise ConcurrentUniverseUpdateError("current generation changed after publication")
        expected_attempt = published.attempt_id
        rounds: list[dict[str, object]] = []
        for candidate in candidates:
            handoff = planner_input(candidate)
            if pack is None:
                plan = build_research_plan(handoff)
                plan_payload = plan.payload()
                research = build_deep_research_package(plan, cutoff=now.isoformat())
            else:
                driver_ids = {driver.driver_id for driver in pack.drivers}
                bindings = tuple(
                    DriverObservationBinding(
                        item.dimension_id, item.member_id, item.dimension_id, item.metric_id,
                        item.unit, item.basis, item.window, item.semantics,
                        timedelta(days=args.maximum_age_days),
                    )
                    for item in current.observations
                    if item.member_id == candidate.member_id and item.dimension_id in driver_ids
                )
                persisted = build_persisted_research_plan(
                    handoff, pack, universe_store=args.store, bindings=bindings
                )
                plan_payload = persisted.payload()
                research = build_deep_research_package(persisted, cutoff=now.isoformat())
            rounds.append({
                "candidate": {
                    **candidate.payload_without_id(), "candidate_id": candidate.candidate_id,
                },
                "plan": plan_payload,
                "research": research.payload(),
                "unavailable": [
                    "company_transmission_requires_research",
                    "counter_thesis_requires_evidence_search",
                    "forecast_not_registered",
                    "human_decision_not_recorded",
                ],
            })
        print(json.dumps({
            "status": "baseline_recorded" if prior is None else "compared",
            "snapshot_id": current.snapshot_id,
            "cutoff_at": now.isoformat(),
            "observations": [item.payload() for item in current.observations],
            "changes": [item.payload() for item in changes],
            "rounds": rounds,
            "official_field_reconciliation": reconciliation,
            "claim_authority": claim_authority,
            "provider_origin_authenticated": False,
            "independent_authority_established": False,
            "product_r1_accepted": False,
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except ConcurrentUniverseUpdateError as exc:
        print(json.dumps({"status": "superseded", "error": str(exc)}, ensure_ascii=False))
        return 2
    except (OSError, ValueError) as exc:
        try:
            publish_failed_universe_attempt(
                output_root=args.store, attempted_at=datetime.now(UTC),
                research_cutoff_at=now, failure_code="r1_source_or_planning_failure",
                expected_current_attempt_id=expected_attempt,
            )
        except ConcurrentUniverseUpdateError:
            print(json.dumps({"status": "superseded", "error": str(exc)}, ensure_ascii=False))
            return 2
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
