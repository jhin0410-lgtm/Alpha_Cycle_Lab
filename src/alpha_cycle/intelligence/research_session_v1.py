"""Immutable, offline-reconstructable R1 research sessions.

An archive proves exact recorded computation, not provider origin. Current-store
publication and historical replay deliberately use different trust boundaries.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from alpha_cycle.intelligence.deep_research_integration_v1 import build_deep_research_package
from alpha_cycle.intelligence.knowledge_pack_repository_v1 import load_knowledge_pack_json
from alpha_cycle.intelligence.observable_universe import (
    _MANIFEST_DIRECTORY,
    _SNAPSHOT_DIRECTORY,
    CandidateRule,
    ChangeState,
    ConcurrentUniverseUpdateError,
    CurrentUniverseState,
    ObservableUniverseSnapshot,
    PlannerCandidateInput,
    ResearchPriority,
    _encoded,
    _exclusive_universe_write_lock,
    _load_current_universe_state_locked,
    _load_manifest_bound_snapshot,
    _read_regular_file,
    _sha,
    _sha_text,
    _unique_object,
    _write_immutable,
    compare_universe_snapshots,
    planner_input,
    surface_research_candidates,
)
from alpha_cycle.intelligence.persisted_research_plan_v1 import (
    DriverObservationBinding,
    resolve_research_plan,
)
from alpha_cycle.intelligence.research_model_runtime_v1 import KnowledgePack, build_research_plan
from alpha_cycle.research_package_assembler_v2_1 import _link_open_file_at

REPOSITORY = "research_sessions_v1"
UNAVAILABLE = [
    "company_transmission_requires_research",
    "counter_thesis_requires_evidence_search",
    "forecast_not_registered",
    "human_decision_not_recorded",
]
POLICY = {
    "source_origin": "recorded_inputs_only",
    "provider_origin_authenticated": False,
    "independent_authority_established": False,
    "live_authority_reissued": False,
    "product_r1_accepted": False,
}


def _json(content: bytes) -> dict[str, Any]:
    value = json.loads(content, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("session value must be an object")
    return value


def _exact(value: dict[str, Any], fields: set[str]) -> None:
    if set(value) != fields:
        raise ValueError("unknown or missing session fields")


@contextmanager
def _directory(path: Path, *, create: bool = False) -> Iterator[Path]:
    """Pin every directory component without following symlinks (POSIX only)."""
    if os.name != "posix" or not Path("/proc/self/fd").is_dir():
        raise ValueError("research session archives require POSIX descriptor paths")
    absolute = Path(os.path.abspath(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for part in absolute.parts[1:]:
            if create:
                try:
                    os.mkdir(part, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield Path(f"/proc/self/fd/{fd}")
        # Do not report success through a namespace that was replaced mid-write.
        if not os.path.samestat(os.fstat(fd), os.stat(absolute, follow_symlinks=False)):
            raise ValueError("session directory changed during operation")
        cursor = absolute
        while cursor != cursor.parent:
            if cursor.is_symlink():
                raise ValueError("session directory ancestor became a symlink")
            cursor = cursor.parent
    finally:
        os.close(fd)


@contextmanager
def _child_directory(
    parent: Path,
    relative: str,
    *,
    create: bool = False,
) -> Iterator[Path]:
    """Open descendants relative to an already pinned directory descriptor."""
    fd = os.dup(int(parent.name))
    try:
        for part in Path(relative).parts:
            if part in {"..", ".", "/"}:
                raise ValueError("child path must contain only normal components")
            if create:
                try:
                    os.mkdir(part, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield Path(f"/proc/self/fd/{fd}")
        if not os.path.samestat(
            os.fstat(fd),
            os.stat(parent / relative, follow_symlinks=False),
        ):
            raise ValueError("session child directory changed during operation")
    finally:
        os.close(fd)


def _generation(state: CurrentUniverseState) -> dict[str, object]:
    if not state.ready or state.snapshot is None:
        raise ValueError("session generation must be successful")
    return {
        "snapshot_id": state.snapshot.snapshot_id,
        "manifest_id": state.last_successful_manifest_id,
        "attempted_at": state.attempted_at.isoformat(),
        "attempt_id": state.attempt_id,
    }


def _preceding_attempt(state: CurrentUniverseState | None) -> dict[str, object] | None:
    if state is None:
        return None
    return {
        "status": state.status.value,
        "attempted_at": state.attempted_at.isoformat(),
        "attempt_id": state.attempt_id,
        "research_cutoff_at": state.research_cutoff_at.isoformat(),
        "failure_code": state.failure_code,
        "last_successful_snapshot_id": state.last_successful_snapshot_id,
        "last_successful_manifest_id": state.last_successful_manifest_id,
    }


def _validate_predecessor(payload: dict[str, Any], parent: str | None) -> None:
    previous = payload["preceding_attempt"]
    prior = payload["comparison_prior_generation"]
    if previous is None:
        if parent is not None or prior is not None:
            raise ValueError("initial session cannot omit its preceding attempt")
        return
    _exact(
        previous,
        {
            "status",
            "attempted_at",
            "attempt_id",
            "research_cutoff_at",
            "failure_code",
            "last_successful_snapshot_id",
            "last_successful_manifest_id",
        },
    )
    attempted = datetime.fromisoformat(previous["attempted_at"])
    cutoff = datetime.fromisoformat(previous["research_cutoff_at"])
    current_time = datetime.fromisoformat(payload["current_generation"]["attempted_at"])
    if attempted.tzinfo is None or cutoff.tzinfo is None or not cutoff <= attempted <= current_time:
        raise ValueError("preceding attempt chronology mismatch")
    if (previous["last_successful_snapshot_id"] is None) != (parent is None):
        raise ValueError("preceding snapshot and manifest must be present together")
    if previous["last_successful_manifest_id"] != parent:
        raise ValueError("preceding attempt does not bind the parent manifest")
    if previous["status"] == "succeeded":
        generation = {
            "snapshot_id": previous["last_successful_snapshot_id"],
            "manifest_id": previous["last_successful_manifest_id"],
            "attempted_at": previous["attempted_at"],
            "attempt_id": previous["attempt_id"],
        }
        if previous["failure_code"] is not None or _encoded(prior) != _encoded(generation):
            raise ValueError("successful predecessor requires exact comparison generation")
        if prior is None:
            raise ValueError("successful predecessor cannot be a recovery baseline")
    elif previous["status"] == "failed":
        if (
            prior is not None
            or not isinstance(previous["failure_code"], str)
            or not previous["failure_code"].strip()
        ):
            raise ValueError("failed predecessor must preserve an explicit recovery baseline")
        expected = _sha(
            {
                "status": "failed",
                "attempted_at": attempted.isoformat(),
                "failure_code": previous["failure_code"],
                "research_cutoff_at": cutoff.isoformat(),
            }
        )
        if expected != previous["attempt_id"]:
            raise ValueError("preceding failure identity mismatch")
    else:
        raise ValueError("unsupported preceding attempt status")


def _archive(root: Path, manifest_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    while True:
        _sha_text(manifest_id, "manifest_id")
        if manifest_id in seen:
            raise ValueError("session manifest ancestry cycle")
        seen.add(manifest_id)
        with _child_directory(root, _MANIFEST_DIRECTORY) as manifests:
            manifest_bytes = _read_regular_file(manifests / f"{manifest_id}.json", "manifest")
        manifest = _json(manifest_bytes)
        snapshot_id = manifest["snapshot_id"]
        _sha_text(snapshot_id, "snapshot_id")
        with _child_directory(root, _SNAPSHOT_DIRECTORY) as snapshots:
            snapshot_bytes = _read_regular_file(snapshots / f"{snapshot_id}.json", "snapshot")
        rows.append(
            {
                "manifest_id": manifest_id,
                "manifest_bytes": base64.b64encode(manifest_bytes).decode("ascii"),
                "snapshot_bytes": base64.b64encode(snapshot_bytes).decode("ascii"),
            }
        )
        parent = manifest["previous_successful_manifest_id"]
        if parent is None:
            return rows
        manifest_id = parent


@dataclass(frozen=True)
class ResearchSession:
    """Canonical archived bytes; callers cannot mutate the validated payload in place."""

    content: bytes

    @property
    def payload(self) -> dict[str, Any]:
        return _json(self.content)

    @property
    def session_id(self) -> str:
        return str(self.payload["session_id"])

    @property
    def rounds(self) -> list[dict[str, Any]]:
        return list(self.payload["rounds"])


def _rules(rows: list[dict[str, Any]]) -> tuple[CandidateRule, ...]:
    for row in rows:
        _exact(
            row,
            {"rule_id", "dimension_id", "states", "priority", "reason", "minimum_absolute_delta"},
        )
        if any(
            not isinstance(row[key], str)
            for key in (
                "rule_id",
                "dimension_id",
                "priority",
                "reason",
            )
        ) or not isinstance(row["states"], list):
            raise ValueError("invalid candidate rule field types")
    if len({row["rule_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate candidate rule IDs")
    result = tuple(
        CandidateRule(
            row["rule_id"],
            row["dimension_id"],
            tuple(ChangeState(x) for x in row["states"]),
            ResearchPriority(row["priority"]),
            row["reason"],
            row["minimum_absolute_delta"],
        )
        for row in rows
    )
    if _encoded([rule.payload() for rule in result]) != _encoded(rows):
        raise ValueError("noncanonical or unknown candidate rule fields")
    return result


def _bindings(rows: list[dict[str, Any]]) -> tuple[DriverObservationBinding, ...]:
    result: list[DriverObservationBinding] = []
    for row in rows:
        age = row["maximum_age_microseconds"]
        if type(age) is not int:
            raise ValueError("binding age must be integer microseconds")
        result.append(
            DriverObservationBinding(
                row["driver_id"],
                row["member_id"],
                row["dimension_id"],
                row["metric_id"],
                row["unit"],
                row["basis"],
                row["window"],
                row["semantics"],
                timedelta(microseconds=age),
            )
        )
    if _encoded([item.payload() for item in result]) != _encoded(rows):
        raise ValueError("noncanonical or unknown binding fields")
    return tuple(result)


def _load_generation(root: Path, generation: dict[str, Any]) -> ObservableUniverseSnapshot:
    _exact(generation, {"snapshot_id", "manifest_id", "attempted_at", "attempt_id"})
    snapshot = _load_manifest_bound_snapshot(
        root,
        generation["snapshot_id"],
        generation["manifest_id"],
        label="session",
    )
    attempted = datetime.fromisoformat(generation["attempted_at"])
    if attempted.tzinfo is None or attempted < snapshot.research_cutoff_at:
        raise ValueError("session attempt precedes its cutoff")
    if (
        _sha(
            {
                "status": "succeeded",
                "attempted_at": attempted.isoformat(),
                "snapshot_id": snapshot.snapshot_id,
                "manifest_id": generation["manifest_id"],
            }
        )
        != generation["attempt_id"]
    ):
        raise ValueError("session generation attempt identity mismatch")
    return snapshot


def _reconstruct(payload: dict[str, Any]) -> dict[str, object]:
    """Recompute measured discovery, explicit requests, plans and packages offline."""
    current_gen = payload["current_generation"]
    prior_gen = payload["comparison_prior_generation"]
    archive = payload["universe_archive"]
    if not isinstance(archive, list) or not archive:
        raise ValueError("session requires complete universe ancestry")
    # Private staging is not the live store and has no current pointer.
    with tempfile.TemporaryDirectory(prefix="acl-session-replay-") as temporary:
        root = Path(temporary)
        (root / _MANIFEST_DIRECTORY).mkdir(parents=True)
        (root / _SNAPSHOT_DIRECTORY).mkdir(parents=True)
        expected_manifest = current_gen["manifest_id"]
        for row in archive:
            _exact(row, {"manifest_id", "manifest_bytes", "snapshot_bytes"})
            if row["manifest_id"] != expected_manifest:
                raise ValueError("session manifest ancestry order mismatch")
            _sha_text(expected_manifest, "manifest_id")
            manifest_bytes = base64.b64decode(row["manifest_bytes"], validate=True)
            snapshot_bytes = base64.b64decode(row["snapshot_bytes"], validate=True)
            manifest = _json(manifest_bytes)
            snapshot_id = manifest["snapshot_id"]
            _sha_text(snapshot_id, "snapshot_id")
            _write_immutable(
                root / _MANIFEST_DIRECTORY / f"{expected_manifest}.json", manifest_bytes
            )
            _write_immutable(root / _SNAPSHOT_DIRECTORY / f"{snapshot_id}.json", snapshot_bytes)
            expected_manifest = manifest["previous_successful_manifest_id"]
        if expected_manifest is not None:
            raise ValueError("session is missing parent manifests")
        parent = _json(base64.b64decode(archive[0]["manifest_bytes"]))[
            "previous_successful_manifest_id"
        ]
        _validate_predecessor(payload, parent)
        current = _load_generation(root, current_gen)
        previous_attempt = payload["preceding_attempt"]
        if (
            previous_attempt is not None
            and datetime.fromisoformat(previous_attempt["research_cutoff_at"])
            > current.research_cutoff_at
        ):
            raise ValueError("session cutoff regresses its preceding attempt")
        prior = None if prior_gen is None else _load_generation(root, prior_gen)
        previous = payload["preceding_attempt"]
        if parent is not None:
            manifest = _json((root / _MANIFEST_DIRECTORY / f"{parent}.json").read_bytes())
            parent_snapshot = _load_manifest_bound_snapshot(
                root,
                manifest["snapshot_id"],
                parent,
                label="preceding session",
            )
            if previous["last_successful_snapshot_id"] != parent_snapshot.snapshot_id:
                raise ValueError("preceding snapshot differs from parent manifest")
            previous_cutoff = datetime.fromisoformat(previous["research_cutoff_at"])
            if previous_cutoff < parent_snapshot.research_cutoff_at:
                raise ValueError("preceding cutoff predates parent snapshot")
            if prior is not None and previous_cutoff != prior.research_cutoff_at:
                raise ValueError("preceding success cutoff differs from its snapshot")
        # A fresh baseline after failure is explicitly not a comparison with the
        # last historical success. Its older ancestors are retained, not used.
        rules = _rules(payload["candidate_rules"])
        changes = () if prior is None else compare_universe_snapshots(prior, current)
        candidates = (
            ()
            if prior is None
            else surface_research_candidates(
                current,
                changes,
                rules,
                prior_snapshot=prior,
            )
        )
        packs = payload["knowledge_packs"]
        policies = payload["binding_policies"]
        if not isinstance(packs, dict) or not isinstance(policies, dict):
            raise ValueError("session packs and policies must be objects")
        requests = payload["explicit_requests"]
        if not isinstance(requests, list):
            raise ValueError("explicit requests must be an array")
        work: list[tuple[PlannerCandidateInput, dict[str, object], str]] = []
        for candidate in candidates:
            work.append(
                (
                    planner_input(candidate),
                    {
                        "candidate": {
                            **candidate.payload_without_id(),
                            "candidate_id": candidate.candidate_id,
                        },
                    },
                    candidate.member_id,
                )
            )
        members = {member.member_id: member for member in current.members}
        seen: set[str] = set()
        for request in requests:
            _exact(request, {"member_id", "reason"})
            member_id, reason = request["member_id"], request["reason"]
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("explicit research request requires a reason")
            if member_id in seen or member_id not in members:
                raise ValueError("duplicate or foreign explicit request member")
            seen.add(member_id)
            member = members[member_id]
            request_payload = {
                **request,
                "current_snapshot_id": current.snapshot_id,
                "current_manifest_id": current_gen["manifest_id"],
                "semantics": "explicit_research_not_measured_discovery",
            }
            request_id = _sha(request_payload)
            # Existing plan/package field names use candidate_id. For requests it
            # contains request_id, while candidate_lineage is explicitly absent.
            handoff = PlannerCandidateInput(
                request_id,
                current.snapshot_id if prior is None else prior.snapshot_id,
                current.snapshot_id,
                member_id,
                member.kind,
                member.domain_id,
                ResearchPriority.ROUTINE,
                current.research_cutoff_at,
                (),
                (),
                (f"Explicit research request: {reason}",),
                (),
                member.required_dimensions,
                member.unavailable_dimensions,
                (),
                member.research_model_status,
                None,
            )
            work.append(
                (handoff, {"request": {**request_payload, "request_id": request_id}}, member_id)
            )
        if set(packs) != set(members) or set(policies) != set(members):
            raise ValueError("session pack/policy scope differs from universe members")
        parsed_packs: dict[str, KnowledgePack | None] = {}
        parsed_bindings: dict[str, tuple[DriverObservationBinding, ...]] = {}
        for member_id in members:
            pack = (
                None
                if packs[member_id] is None
                else load_knowledge_pack_json(
                    json.dumps(packs[member_id], allow_nan=False),
                )
            )
            if pack is not None and pack.domain_id != members[member_id].domain_id:
                raise ValueError("knowledge pack does not match member domain")
            parsed_packs[member_id] = pack
            parsed_bindings[member_id] = _bindings(policies[member_id])
            if pack is None and parsed_bindings[member_id]:
                raise ValueError("bindings require a knowledge pack")
        rounds: list[dict[str, object]] = []
        for handoff, entry, member_id in work:
            pack = parsed_packs[member_id]
            bindings = parsed_bindings[member_id]
            if pack is None:
                if bindings:
                    raise ValueError("bindings require a knowledge pack")
                plan = build_research_plan(handoff)
                if "request" in entry:
                    plan = replace(plan, candidate_lineage=None)
                plan_payload, plan_id = plan.payload(), plan.content_id
                research = build_deep_research_package(
                    plan, cutoff=current.research_cutoff_at.isoformat()
                )
            else:
                resolved = resolve_research_plan(handoff, pack, snapshot=current, bindings=bindings)
                if "request" in entry:
                    resolved = replace(
                        resolved, plan=replace(resolved.plan, candidate_lineage=None)
                    )
                plan_payload, plan_id = resolved.payload(), resolved.content_id
                research = build_deep_research_package(
                    resolved,
                    cutoff=current.research_cutoff_at.isoformat(),
                )
            rounds.append(
                {
                    **entry,
                    "plan": plan_payload,
                    "plan_content_id": plan_id,
                    "research": research.payload(),
                    "unavailable": list(UNAVAILABLE),
                }
            )
        return {
            "status": "baseline_recorded" if prior is None else "compared",
            "snapshot_id": current.snapshot_id,
            "cutoff_at": current.research_cutoff_at.isoformat(),
            "changes": [item.payload() for item in changes],
            "rounds": rounds,
        }


def _validate(payload: dict[str, Any]) -> ResearchSession:
    _exact(
        payload,
        {
            "schema_version",
            "session_id",
            "current_generation",
            "comparison_prior_generation",
            "preceding_attempt",
            "universe_archive",
            "candidate_rules",
            "knowledge_packs",
            "binding_policies",
            "explicit_requests",
            "source_receipts_json",
            "authority_policy",
            "status",
            "snapshot_id",
            "cutoff_at",
            "changes",
            "rounds",
        },
    )
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("unsupported research session schema")
    if _encoded(payload["authority_policy"]) != _encoded(POLICY):
        raise ValueError("session cannot reissue source authority")
    receipts = payload["source_receipts_json"]
    if not isinstance(receipts, str) or _encoded(_json(receipts.encode())).decode() != receipts:
        raise ValueError("source receipts must be canonical archival JSON, not live authority")
    without_id = {key: value for key, value in payload.items() if key != "session_id"}
    if _sha(without_id) != payload["session_id"]:
        raise ValueError("research session content identity mismatch")
    reconstructed = _reconstruct(payload)
    for key, value in reconstructed.items():
        if _encoded(value) != _encoded(payload[key]):
            raise ValueError(f"session reconstructed {key} differs from recorded output")
    return ResearchSession(_encoded(payload))


def persist_research_session(
    *,
    universe_store: Path,
    current: CurrentUniverseState,
    comparison_prior: CurrentUniverseState | None,
    rules: tuple[CandidateRule, ...],
    packs: dict[str, KnowledgePack | None],
    bindings: dict[str, tuple[DriverObservationBinding, ...]],
    explicit_requests: tuple[tuple[str, str], ...] = (),
    preceding_attempt: CurrentUniverseState | None = None,
    source_receipts: dict[str, object] | None = None,
) -> tuple[ResearchSession, Path]:
    """Publish one atomic bundle only while its exact universe attempt is current.

    Identical calls reuse identical bytes; no mutable session latest pointer exists.
    """
    with _directory(universe_store) as pinned:
        with _exclusive_universe_write_lock(pinned, directory_prepared=True):
            observed = _load_current_universe_state_locked(pinned)
            if observed != current or not current.ready:
                raise ConcurrentUniverseUpdateError("session universe generation was superseded")
            generation = _generation(current)
            payload: dict[str, Any] = {
                "schema_version": 1,
                "current_generation": generation,
                "preceding_attempt": _preceding_attempt(
                    preceding_attempt if preceding_attempt is not None else comparison_prior
                ),
                "comparison_prior_generation": (
                    None if comparison_prior is None else _generation(comparison_prior)
                ),
                "universe_archive": _archive(pinned, str(generation["manifest_id"])),
                "candidate_rules": [rule.payload() for rule in rules],
                "knowledge_packs": {
                    key: None if pack is None else pack.payload() for key, pack in packs.items()
                },
                "binding_policies": {
                    key: [item.payload() for item in policy] for key, policy in bindings.items()
                },
                "explicit_requests": [
                    {"member_id": key, "reason": reason} for key, reason in explicit_requests
                ],
                "source_receipts_json": _encoded(source_receipts or {}).decode(),
                "authority_policy": dict(POLICY),
            }
            payload.update(_reconstruct(payload))
            payload["session_id"] = _sha(payload)
            session = _validate(payload)
            destination = universe_store / REPOSITORY / f"{session.session_id}.json"
            with _child_directory(pinned, REPOSITORY, create=True) as repository:
                # Existing immutable writer produces/fsyncs a complete private
                # stage. Publish its held inode, never a substitutable temp name.
                with tempfile.TemporaryDirectory(
                    prefix="acl-session-write-", dir=repository
                ) as temp:
                    staged = Path(temp) / destination.name
                    _write_immutable(staged, session.content)
                    fd = os.open(staged, os.O_RDONLY | os.O_NOFOLLOW)
                    try:
                        repository_fd = int(repository.name)
                        try:
                            _link_open_file_at(fd, repository_fd, destination.name)
                        except FileExistsError:
                            if (
                                _read_regular_file(repository / destination.name, "session")
                                != session.content
                            ):
                                raise ValueError("immutable session publication conflict") from None
                        os.fsync(repository_fd)
                        if (
                            _read_regular_file(repository / destination.name, "session")
                            != session.content
                        ):
                            raise ValueError("session publication verification failed")
                    finally:
                        os.close(fd)
            return session, destination


def replay_research_session(path: Path) -> ResearchSession:
    """Replay from one portable bundle without a store, network or live issuance."""
    with _directory(path.parent) as directory:
        content = _read_regular_file(directory / path.name, "research session")
    payload = _json(content)
    if path.name != f"{payload.get('session_id')}.json":
        raise ValueError("session filename differs from content identity")
    try:
        return _validate(payload)
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("invalid research session schema") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay an archived R1 research session offline")
    parser.add_argument("--session", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = replay_research_session(args.session)
        print(
            json.dumps(
                {
                    "session_id": result.session_id,
                    "replayed": True,
                    "authority_policy": dict(POLICY),
                    "rounds": result.rounds,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
