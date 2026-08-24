from pathlib import Path

INTEGRITY = Path("src/alpha_cycle/research_package_integrity_v2_1.py")
ASSEMBLER = Path("src/alpha_cycle/research_package_assembler_v2_1.py")
TEST = Path("tests/unit/test_research_package_last_review_v2_1.py")

text = INTEGRITY.read_text(encoding="utf-8")
old = '''def package_integrity_blocker_codes(\n    thesis: InvestmentThesisSnapshot,\n    underwriting: UnderwritingReadinessSnapshot | None,\n    payoff: PayoffSurfaceSnapshot | None,\n    view: DecisionViewSnapshot | None,\n    gap: DecisionExpectationGapSnapshot | None,\n) -> tuple[str, ...]:'''
new = '''def package_integrity_blocker_codes(\n    thesis: InvestmentThesisSnapshot,\n    underwriting: UnderwritingReadinessSnapshot | None,\n    payoff: PayoffSurfaceSnapshot | None,\n    view: DecisionViewSnapshot | None,\n    gap: DecisionExpectationGapSnapshot | None,\n    *,\n    artifact_root: str | Path | None = None,\n) -> tuple[str, ...]:'''
assert old in text
text = text.replace(old, new, 1)
old = '''    if underwriting is not None and not _underwriting_ready_contract_is_valid(\n        thesis, underwriting, payoff\n    ):'''
new = '''    if underwriting is not None and not _underwriting_ready_contract_is_valid(\n        thesis,\n        underwriting,\n        payoff,\n        artifact_root=artifact_root,\n    ):'''
assert old in text
text = text.replace(old, new, 1)
old = '''def _underwriting_ready_contract_is_valid(\n    thesis: InvestmentThesisSnapshot,\n    underwriting: UnderwritingReadinessSnapshot,\n    payoff: PayoffSurfaceSnapshot | None,\n) -> bool:'''
new = '''def _underwriting_ready_contract_is_valid(\n    thesis: InvestmentThesisSnapshot,\n    underwriting: UnderwritingReadinessSnapshot,\n    payoff: PayoffSurfaceSnapshot | None,\n    *,\n    artifact_root: str | Path | None = None,\n) -> bool:'''
assert old in text
text = text.replace(old, new, 1)
old = '''        required = tuple(active.fast_lane_required_elements)\n        return bool(\n            tuple(underwriting.required_elements_satisfied) == required\n            and not underwriting.required_elements_missing\n            and not underwriting.blockers\n        )\n'''
new = '''        required = tuple(active.fast_lane_required_elements)\n        base_contract = bool(\n            tuple(underwriting.required_elements_satisfied) == required\n            and not underwriting.required_elements_missing\n            and not underwriting.blockers\n        )\n        if not base_contract:\n            return False\n        if artifact_root is None:\n            return True\n        return _fast_lane_persisted_evidence_is_valid(\n            Path(artifact_root),\n            thesis=thesis,\n            underwriting=underwriting,\n        )\n'''
assert old in text
text = text.replace(old, new, 1)
marker = '''\ndef _gap_observations_match_view(\n'''
assert marker in text
helper = r'''

def _fast_lane_persisted_evidence_is_valid(
    root: Path,
    *,
    thesis: InvestmentThesisSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
) -> bool:
    """Substantiate the canonical Fast-Lane evidence contract from persisted artifacts."""

    context = _load_bound_evidence_payload(
        root,
        repository_name="underwriting_context",
        snapshot_id=underwriting.context_snapshot_id,
        payload_name="underwriting_context.json",
    )
    if context is None:
        return False
    if (
        context.get("thesis_snapshot_id") != thesis.snapshot_id
        or context.get("security_id") != thesis.security_id
        or context.get("evaluation_date") != underwriting.evaluation_date.isoformat()
        or context.get("guardrail_evidence_id") != underwriting.guardrail_evidence_id
    ):
        return False
    try:
        if _payload_datetime(context, "captured_at") > underwriting.captured_at:
            return False
    except (TypeError, ValueError):
        return False
    transmission_refs = context.get("transmission_evidence_refs")
    transmission_bound = bool(
        isinstance(transmission_refs, list)
        and transmission_refs
        and all(isinstance(item, str) and item.strip() for item in transmission_refs)
    )
    if not transmission_bound and underwriting.causal_graph_snapshot_id is not None:
        graph = _load_bound_evidence_payload(
            root,
            repository_name="semiconductor_causal_graph",
            snapshot_id=underwriting.causal_graph_snapshot_id,
            payload_name="causal_graph.json",
        )
        if graph is not None:
            try:
                transmission_bound = bool(
                    graph.get("security_id") in {None, thesis.security_id}
                    and graph.get("evaluation_date")
                    == underwriting.evaluation_date.isoformat()
                    and graph.get("guardrail_evidence_id")
                    == underwriting.guardrail_evidence_id
                    and _payload_datetime(graph, "captured_at")
                    <= underwriting.captured_at
                )
            except (TypeError, ValueError):
                transmission_bound = False
    if not transmission_bound:
        return False

    expectation_bound = False
    if underwriting.expectation_state_snapshot_id is not None:
        expectation = _load_bound_evidence_payload(
            root,
            repository_name="expectation_state",
            snapshot_id=underwriting.expectation_state_snapshot_id,
            payload_name="expectations.json",
        )
        if expectation is not None:
            observations = expectation.get("observations")
            try:
                expectation_bound = bool(
                    expectation.get("evaluation_date")
                    == underwriting.evaluation_date.isoformat()
                    and _payload_datetime(expectation, "captured_at")
                    <= underwriting.captured_at
                    and isinstance(observations, list)
                    and any(
                        isinstance(item, dict)
                        and item.get("security_id") == thesis.security_id
                        for item in observations
                    )
                )
            except (TypeError, ValueError):
                expectation_bound = False
    if not expectation_bound and underwriting.price_implied_requirement_snapshot_id is not None:
        price_implied = _load_bound_evidence_payload(
            root,
            repository_name="price_implied_requirement",
            snapshot_id=underwriting.price_implied_requirement_snapshot_id,
            payload_name="price_implied_requirement.json",
        )
        if price_implied is not None:
            observations = price_implied.get("observations")
            try:
                expectation_bound = bool(
                    price_implied.get("security_id") == thesis.security_id
                    and price_implied.get("evaluation_date")
                    == underwriting.evaluation_date.isoformat()
                    and price_implied.get("guardrail_evidence_id")
                    == underwriting.guardrail_evidence_id
                    and _payload_datetime(price_implied, "captured_at")
                    <= underwriting.captured_at
                    and isinstance(observations, list)
                    and any(
                        isinstance(item, dict)
                        and item.get("security_id") == thesis.security_id
                        and item.get("status") == "available"
                        for item in observations
                    )
                )
            except (TypeError, ValueError):
                expectation_bound = False
    if not expectation_bound:
        return False

    if underwriting.epistemic_defense_snapshot_id is None:
        return False
    epistemic = _load_bound_evidence_payload(
        root,
        repository_name="epistemic_package",
        snapshot_id=underwriting.epistemic_defense_snapshot_id,
        payload_name="epistemic_package.json",
    )
    if epistemic is None:
        return False
    try:
        return bool(
            epistemic.get("thesis_snapshot_id") == thesis.snapshot_id
            and epistemic.get("guardrail_evidence_id")
            == underwriting.guardrail_evidence_id
            and epistemic.get("required_contracts_present") is True
            and _payload_datetime(epistemic, "captured_at")
            <= underwriting.captured_at
        )
    except (TypeError, ValueError):
        return False


def _load_bound_evidence_payload(
    root: Path,
    *,
    repository_name: str,
    snapshot_id: str,
    payload_name: str,
) -> dict[str, object] | None:
    """Load one immutable content-addressed evidence payload from a contained repository."""

    try:
        resolved_root = require_trusted_artifact_root(root)
        repository = root / repository_name
        _require_safe_repository(
            repository,
            resolved_root=resolved_root,
            label=repository_name,
        )
        if not repository.exists():
            return None
        matches = tuple(
            path
            for path in repository.iterdir()
            if path.is_dir()
            and not path.name.startswith(".")
            and path.name.endswith(f"__{snapshot_id[:12]}")
        )
        if len(matches) != 1:
            return None
        directory = matches[0]
        _require_safe_directory_slot(directory, repository, repository_name)
        payload_path = directory / payload_name
        manifest_path = directory / "manifest.json"
        _require_safe_file_slot(payload_path, directory, f"{repository_name} payload")
        _require_safe_file_slot(manifest_path, directory, f"{repository_name} manifest")
        payload = _load_json_object(payload_path)
        manifest = _load_json_object(manifest_path)
    except (OSError, ResearchPackageIntegrityError):
        return None
    if _sha(payload) != snapshot_id:
        return None
    if manifest.get("snapshot_id") != snapshot_id:
        return None
    files = manifest.get("files")
    if not isinstance(files, list) or payload_name not in files:
        return None
    captured_at = payload.get("captured_at")
    if manifest.get("captured_at") != captured_at:
        return None
    return payload
'''
text = text.replace(marker, helper + marker, 1)
INTEGRITY.write_text(text, encoding="utf-8")

text = ASSEMBLER.read_text(encoding="utf-8")
old = '''    for code in package_integrity_blocker_codes(thesis, underwriting, payoff, view, gap):\n'''
new = '''    for code in package_integrity_blocker_codes(\n        thesis,\n        underwriting,\n        payoff,\n        view,\n        gap,\n        artifact_root=artifact_root,\n    ):\n'''
assert old in text
text = text.replace(old, new, 1)
ASSEMBLER.write_text(text, encoding="utf-8")

text = TEST.read_text(encoding="utf-8")
addition = r'''


def test_fast_ready_requires_persisted_evidence_bindings(tmp_path: Path) -> None:
    active = integrity.load_decision_system_v21_guardrails()
    thesis = SimpleNamespace(
        snapshot_id=A,
        security_id="000660",
        status=ThesisStatus.UNDERWRITING,
    )
    underwriting = SimpleNamespace(
        readiness=UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW,
        lane=UnderwritingLane.FAST,
        evaluation_date=EVAL,
        captured_at=NOW,
        context_snapshot_id=B,
        causal_graph_snapshot_id=None,
        expectation_state_snapshot_id=None,
        price_implied_requirement_snapshot_id=None,
        epistemic_defense_snapshot_id=None,
        guardrail_evidence_id=active.evidence_id,
        required_elements_satisfied=tuple(active.fast_lane_required_elements),
        required_elements_missing=(),
        blockers=(),
    )

    assert not integrity._underwriting_ready_contract_is_valid(  # type: ignore[attr-defined]
        thesis,  # type: ignore[arg-type]
        underwriting,  # type: ignore[arg-type]
        None,
        artifact_root=tmp_path,
    )
'''
if "test_fast_ready_requires_persisted_evidence_bindings" not in text:
    text += addition
TEST.write_text(text, encoding="utf-8")
