from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match in {path}, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    target.write_text(text[:start_index] + replacement + text[end_index:], encoding="utf-8")


integrity = "src/alpha_cycle/research_package_integrity_v2_1.py"
assembler = "src/alpha_cycle/research_package_assembler_v2_1.py"
assembler_test = "tests/unit/test_research_package_assembler_v2_1.py"
final_test = "tests/unit/test_research_package_codex_final_gate_v2_1.py"

# 1 + 4: canonical reconstruction of registrations and persisted Decision View selection rule.
replace_once(
    integrity,
    "from alpha_cycle.intelligence.decision_view_v2_1 import (\n    DecisionExpectationGapSnapshot,\n    DecisionViewSnapshot,\n)\nfrom alpha_cycle.intelligence.forecast_ledger import (\n    FORECAST_LEDGER_SCHEMA_VERSION,\n    ForecastRegistrationMode,\n)\n",
    "from alpha_cycle.intelligence.decision_view_v2_1 import (\n    DECISION_VIEW_SCHEMA_VERSION,\n    DecisionExpectationGapSnapshot,\n    DecisionViewSelectionMethod,\n    DecisionViewSelectionRuleSnapshot,\n    DecisionViewSnapshot,\n)\nfrom alpha_cycle.intelligence.forecast_ledger import (\n    FORECAST_LEDGER_SCHEMA_VERSION,\n    ForecastDirection,\n    ForecasterKind,\n    ForecastRegistrationMode,\n    ForecastRegistrationSnapshot,\n    OrdinalAssessment,\n    PrimaryErrorMetric,\n)\n",
)

new_tournament = '''def _persisted_tournament_registrations_match(
    root: Path,
    *,
    view: DecisionViewSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    snapshot_ids: tuple[str, ...],
    forecast_ids: tuple[str, ...],
) -> bool:
    registrations = _load_persisted_forecast_registrations(root, snapshot_ids)
    if len(registrations) != len(snapshot_ids):
        return False
    descriptors: set[tuple[ForecasterKind, str]] = set()
    clusters: set[str] = set()
    tournament = underwriting.forecast_tournament
    for registration, expected_snapshot_id, expected_forecast_id in zip(
        registrations,
        snapshot_ids,
        forecast_ids,
        strict=True,
    ):
        if registration.snapshot_id != expected_snapshot_id:
            return False
        if registration.forecast_id != expected_forecast_id:
            return False
        if registration.security_id != view.security_id:
            return False
        if registration.target_variable != view.target_variable:
            return False
        if registration.target_date != view.target_date:
            return False
        if registration.unit != view.unit:
            return False
        if registration.primary_error_metric.value != tournament.primary_error_metric:
            return False
        if registration.guardrail_evidence_id != underwriting.guardrail_evidence_id:
            return False
        if not (
            registration.information_cutoff <= registration.registered_at
            <= registration.ledger_recorded_at
            and registration.registered_at <= registration.forecast_origin
            and registration.information_cutoff == view.information_cutoff
            and registration.forecast_origin == view.forecast_origin
            and registration.target_date == view.target_date
            and registration.forecast_origin.date() < registration.target_date
            and registration.ledger_recorded_at <= view.captured_at
        ):
            return False
        descriptors.add((registration.forecaster_kind, registration.model_family))
        clusters.add(registration.dependency_cluster_id)

    if len(descriptors) < 2:
        return False
    if len(descriptors) != tournament.distinct_forecaster_count:
        return False
    if len(clusters) != tournament.dependency_cluster_count:
        return False
    dependency_overlap = len(clusters) < len(registrations)
    if view.tournament_dependency_overlap is not dependency_overlap:
        return False
    expected_tournament_flags = (
        ("forecast_dependency_overlap",) if dependency_overlap else ()
    )
    if tuple(tournament.flags) != expected_tournament_flags:
        return False

    try:
        selected_index = snapshot_ids.index(view.selected_forecast_snapshot_id)
    except ValueError:
        return False
    selected = registrations[selected_index]
    if selected.forecast_id != view.selected_forecast_id:
        return False
    if selected.forecaster_kind is not view.selected_forecaster_kind:
        return False
    if selected.model_family != view.selected_model_family:
        return False
    if not _numbers_match(selected.forecast_value, view.selected_forecast_value):
        return False

    rule = _load_persisted_decision_view_selection_rule(
        root,
        view.selection_rule_snapshot_id,
    )
    if rule is None:
        return False
    if rule.guardrail_evidence_id != underwriting.guardrail_evidence_id:
        return False
    if (
        rule.security_id != view.security_id
        or rule.target_variable != view.target_variable
        or rule.target_date != view.target_date
        or rule.unit != view.unit
    ):
        return False
    if rule.registered_at.date() > view.evaluation_date:
        return False
    if any(rule.registered_at >= item.registered_at for item in registrations):
        return False
    matching_rule_forecasts = tuple(
        item
        for item in registrations
        if item.forecaster_kind is rule.selected_forecaster_kind
        and item.model_family == rule.selected_model_family
    )
    if len(matching_rule_forecasts) != 1:
        return False
    pinned = matching_rule_forecasts[0]
    return bool(
        rule.selection_method is DecisionViewSelectionMethod.PINNED_FORECASTER_IDENTITY
        and pinned.snapshot_id == view.selected_forecast_snapshot_id
        and pinned.forecast_id == view.selected_forecast_id
        and rule.selected_forecaster_kind is view.selected_forecaster_kind
        and rule.selected_model_family == view.selected_model_family
    )


def _load_persisted_forecast_registrations(
    root: Path,
    snapshot_ids: tuple[str, ...],
) -> tuple[ForecastRegistrationSnapshot, ...]:
    resolved_root = require_trusted_artifact_root(root)
    repository = root / "registration"
    _require_safe_repository(
        repository,
        resolved_root=resolved_root,
        label="forecast registration",
    )
    if not repository.exists():
        return ()
    loaded: list[ForecastRegistrationSnapshot] = []
    for snapshot_id in snapshot_ids:
        matches = tuple(
            path
            for path in repository.iterdir()
            if path.is_dir()
            and not path.name.startswith(".")
            and path.name.endswith(f"__{snapshot_id[:12]}")
        )
        if len(matches) != 1:
            return ()
        directory = matches[0]
        _require_safe_directory_slot(
            directory,
            repository,
            "forecast registration",
        )
        payload_path = directory / "forecast_registration.json"
        manifest_path = directory / "manifest.json"
        _require_safe_file_slot(
            payload_path,
            directory,
            "forecast registration payload",
        )
        _require_safe_file_slot(
            manifest_path,
            directory,
            "forecast registration manifest",
        )
        payload = _load_json_object(payload_path)
        manifest = _load_json_object(manifest_path)
        try:
            registration = _reconstruct_forecast_registration(payload)
        except (KeyError, TypeError, ValueError):
            return ()
        if registration.payload_without_id() != payload:
            return ()
        if registration.snapshot_id != snapshot_id or _sha(payload) != snapshot_id:
            return ()
        ledger_recorded_at = registration.ledger_recorded_at
        expected_directory = (
            ledger_recorded_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            + f"__{snapshot_id[:12]}"
        )
        if directory.name != expected_directory:
            return ()
        expected_manifest = {
            "schema_version": FORECAST_LEDGER_SCHEMA_VERSION,
            "object_type": "registration",
            "snapshot_id": snapshot_id,
            "captured_at": ledger_recorded_at.isoformat(),
            "immutable": True,
            "order_api_enabled": False,
            "files": ["forecast_registration.json"],
            "forecast_id": registration.forecast_id,
            "registration_mode": registration.registration_mode.value,
            "dependency_cluster_id": registration.dependency_cluster_id,
            "guardrail_evidence_id": registration.guardrail_evidence_id,
            "outcome_observed": False,
            "evaluation_run": False,
        }
        if manifest != expected_manifest:
            return ()
        loaded.append(registration)
    return tuple(loaded)


def _reconstruct_forecast_registration(
    payload: dict[str, object],
) -> ForecastRegistrationSnapshot:
    direction_raw = payload.get("direction")
    direction = (
        None
        if direction_raw is None
        else ForecastDirection(_payload_text(payload, "direction"))
    )
    return ForecastRegistrationSnapshot(
        forecast_id=_payload_text(payload, "forecast_id"),
        registered_at=_payload_datetime(payload, "registered_at"),
        ledger_recorded_at=_payload_datetime(payload, "ledger_recorded_at"),
        forecast_origin=_payload_datetime(payload, "forecast_origin"),
        information_cutoff=_payload_datetime(payload, "information_cutoff"),
        security_id=_payload_text(payload, "security_id"),
        target_variable=_payload_text(payload, "target_variable"),
        target_date=_payload_date(payload, "target_date"),
        horizon_label=_payload_text(payload, "horizon_label"),
        forecast_value=_payload_float(payload, "forecast_value"),
        unit=_payload_text(payload, "unit"),
        range_lower=_payload_optional_float(payload, "range_lower"),
        range_upper=_payload_optional_float(payload, "range_upper"),
        direction=direction,
        direction_reference_value=_payload_optional_float(
            payload, "direction_reference_value"
        ),
        direction_flat_tolerance=_payload_float(payload, "direction_flat_tolerance"),
        confidence=OrdinalAssessment(_payload_text(payload, "confidence")),
        confidence_rationale=_payload_text(payload, "confidence_rationale"),
        forecaster_kind=ForecasterKind(_payload_text(payload, "forecaster_kind")),
        model_family=_payload_text(payload, "model_family"),
        driver_refs=_payload_text_tuple(payload, "driver_refs"),
        regime_tags=_payload_text_tuple(payload, "regime_tags"),
        decision_relevance=OrdinalAssessment(
            _payload_text(payload, "decision_relevance")
        ),
        difficulty=OrdinalAssessment(_payload_text(payload, "difficulty")),
        baseline_refs=_payload_text_tuple(payload, "baseline_refs"),
        dependency_cluster_id=_payload_text(payload, "dependency_cluster_id"),
        source_evidence_ids=_payload_text_tuple(payload, "source_evidence_ids"),
        registration_mode=ForecastRegistrationMode(
            _payload_text(payload, "registration_mode")
        ),
        primary_error_metric=PrimaryErrorMetric(
            _payload_text(payload, "primary_error_metric")
        ),
        guardrail_evidence_id=_payload_text(payload, "guardrail_evidence_id"),
    )


def _load_persisted_decision_view_selection_rule(
    root: Path,
    snapshot_id: str,
) -> DecisionViewSelectionRuleSnapshot | None:
    resolved_root = require_trusted_artifact_root(root)
    repository = root / "decision_view_selection_rule"
    _require_safe_repository(
        repository,
        resolved_root=resolved_root,
        label="decision view selection rule",
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
    _require_safe_directory_slot(
        directory,
        repository,
        "decision view selection rule",
    )
    payload_path = directory / "decision_view_selection_rule.json"
    manifest_path = directory / "manifest.json"
    _require_safe_file_slot(payload_path, directory, "decision view selection rule payload")
    _require_safe_file_slot(manifest_path, directory, "decision view selection rule manifest")
    payload = _load_json_object(payload_path)
    manifest = _load_json_object(manifest_path)
    try:
        rule = DecisionViewSelectionRuleSnapshot(
            rule_id=_payload_text(payload, "rule_id"),
            registered_at=_payload_datetime(payload, "registered_at"),
            security_id=_payload_text(payload, "security_id"),
            target_variable=_payload_text(payload, "target_variable"),
            target_date=_payload_date(payload, "target_date"),
            unit=_payload_text(payload, "unit"),
            selection_method=DecisionViewSelectionMethod(
                _payload_text(payload, "selection_method")
            ),
            selected_forecaster_kind=ForecasterKind(
                _payload_text(payload, "selected_forecaster_kind")
            ),
            selected_model_family=_payload_text(payload, "selected_model_family"),
            rationale=_payload_text(payload, "rationale"),
            source_evidence_ids=_payload_text_tuple(payload, "source_evidence_ids"),
            guardrail_evidence_id=_payload_text(payload, "guardrail_evidence_id"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if rule.payload_without_id() != payload:
        return None
    if rule.snapshot_id != snapshot_id or _sha(payload) != snapshot_id:
        return None
    expected_directory = (
        rule.registered_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + f"__{snapshot_id[:12]}"
    )
    if directory.name != expected_directory:
        return None
    expected_manifest = {
        "schema_version": DECISION_VIEW_SCHEMA_VERSION,
        "object_type": "decision_view_selection_rule",
        "snapshot_id": snapshot_id,
        "captured_at": rule.registered_at.isoformat(),
        "immutable": True,
        "files": ["decision_view_selection_rule.json"],
        "decision_score_enabled": False,
        "target_price_enabled": False,
        "automatic_execution_enabled": False,
    }
    return rule if manifest == expected_manifest else None


def _payload_text(payload: dict[str, object], field: str) -> str:
    raw = payload[field]
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} must be non-empty text")
    return raw


def _payload_text_tuple(payload: dict[str, object], field: str) -> tuple[str, ...]:
    raw = payload[field]
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise ValueError(f"{field} must be a list of strings")
    return tuple(raw)


def _payload_date(payload: dict[str, object], field: str) -> date:
    return date.fromisoformat(_payload_text(payload, field))


def _payload_float(payload: dict[str, object], field: str) -> float:
    raw = payload[field]
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ValueError(f"{field} must be numeric")
    return float(raw)


def _payload_optional_float(payload: dict[str, object], field: str) -> float | None:
    raw = payload[field]
    if raw is None:
        return None
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ValueError(f"{field} must be numeric or null")
    return float(raw)


'''
replace_between(
    integrity,
    "def _persisted_tournament_registrations_match(\n",
    "def _payload_datetime(payload: dict[str, object], field: str) -> datetime:\n",
    new_tournament,
)

# 2: ownership-safe monotonic opportunity publication and rollback.
replace_once(
    assembler,
    "import shutil\nfrom dataclasses import dataclass\n",
    "import json\nimport os\nimport shutil\nfrom dataclasses import dataclass\n",
)
replace_once(
    assembler,
    "from alpha_cycle.intelligence.opportunity_set_v2_1 import (\n    persist_opportunity_candidate,\n    persist_opportunity_set,\n)\n",
    "from alpha_cycle.intelligence.opportunity_set_v2_1 import (\n    OPPORTUNITY_SET_SCHEMA_VERSION,\n    OpportunityCandidateSnapshot,\n    OpportunitySetSnapshot,\n)\n",
)

receipt_anchor = "@dataclass(frozen=True)\nclass ResearchPackageAssemblyReceipt:\n"
owned_receipt = '''@dataclass(frozen=True)
class _OwnedOpportunityPublication:
    root: Path
    directory: Path
    directory_created: bool
    root_created: bool
    pointer: Path
    pointer_before: bytes | None
    pointer_after: bytes
    pointer_inode: int
    pointer_mtime_ns: int
    pointer_size: int


'''
replace_once(assembler, receipt_anchor, owned_receipt + receipt_anchor)

# 3: stale/missing thesis becomes persisted structured blocker rather than an early exception.
replace_once(
    assembler,
    "        if tuple(resolved_thesis_ids) != preflight.thesis_snapshot_ids:\n            raise ValueError(\n                \"current thesis preflight no longer matches PIT-selected thesis snapshots\"\n            )\n",
    "        if tuple(resolved_thesis_ids) != preflight.thesis_snapshot_ids:\n            _block(\n                blockers,\n                \"thesis\",\n                \"preflight_thesis_identity_mismatch\",\n                None,\n            )\n",
)

new_publish = '''def _publish_orchestrated_artifacts(
    *,
    artifacts: ResearchRoundArtifacts,
    run: ResearchRoundRunSnapshot,
    ledger: ResearchRunLedgerSnapshot,
    root: Path,
) -> tuple[Path, Path, Path]:
    validate_publication_layout(root, artifacts=artifacts, run=run, ledger=ledger)
    validate_existing_opportunity_artifacts(root, artifacts)

    opportunity_publications: list[_OwnedOpportunityPublication] = []
    round_path: Path | None = None
    run_path: Path | None = None
    try:
        for candidate in artifacts.opportunity_candidates:
            publication = _persist_owned_opportunity_snapshot(candidate, output_root=root)
            opportunity_publications.append(publication)
            validate_persisted_opportunity_candidate(
                root,
                candidate,
                require_pointer=_pointer_version_is_current(publication),
            )
        if artifacts.opportunity_set is not None:
            publication = _persist_owned_opportunity_snapshot(
                artifacts.opportunity_set,
                output_root=root,
            )
            opportunity_publications.append(publication)
            validate_persisted_opportunity_set(
                root,
                artifacts.opportunity_set,
                require_pointer=_pointer_version_is_current(publication),
            )
        round_path = persist_research_round(artifacts.snapshot, output_root=root)
        run_path = persist_research_run(run, output_root=root)
        ledger_path = persist_research_run_ledger(ledger, output_root=root)
        return round_path, run_path, ledger_path
    except BaseException as exc:
        cleanup_errors: list[BaseException] = []
        for path in (run_path, round_path):
            if path is None:
                continue
            try:
                path.unlink(missing_ok=True)
            except BaseException as cleanup_exc:
                cleanup_errors.append(cleanup_exc)
        for publication in reversed(opportunity_publications):
            _rollback_owned_opportunity_publication(publication, cleanup_errors)
        if cleanup_errors:
            raise RuntimeError(
                "orchestrated research publication failed and rollback was incomplete"
            ) from cleanup_errors[0]
        raise exc


def _persist_owned_opportunity_snapshot(
    snapshot: OpportunityCandidateSnapshot | OpportunitySetSnapshot,
    *,
    output_root: Path,
) -> _OwnedOpportunityPublication:
    if isinstance(snapshot, OpportunityCandidateSnapshot):
        object_name = "opportunity_candidate"
        manifest_extra: dict[str, object] = {
            "security_id": snapshot.security_id,
            "research_class": snapshot.research_class.value,
            "capital_allocation_comparable": snapshot.capital_allocation_comparable,
        }
    else:
        object_name = "opportunity_set"
        manifest_extra = {
            "evaluation_date": snapshot.evaluation_date.isoformat(),
            "horizon_trading_days": snapshot.horizon_trading_days,
            "candidate_count": len(snapshot.candidates),
            "comparable_candidate_count": len(snapshot.comparable_security_ids),
            "pareto_frontier_security_ids": list(snapshot.pareto_frontier_security_ids),
            "unique_pareto_leader_security_id": snapshot.unique_pareto_leader_security_id,
            "capital_allocation_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }
    root = output_root / object_name
    root_created = not root.exists()
    root.mkdir(parents=True, exist_ok=True)
    directory = _opportunity_snapshot_directory(
        output_root,
        object_name=object_name,
        captured_at=snapshot.captured_at,
        snapshot_id=snapshot.snapshot_id,
    )
    directory_created = False
    if not directory.exists():
        temporary = root / f".{directory.name}.{os.getpid()}.owned.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            manifest = {
                "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
                "object_type": object_name,
                "snapshot_id": snapshot.snapshot_id,
                "captured_at": snapshot.captured_at.isoformat(),
                "immutable": True,
                "files": [f"{object_name}.json"],
                **manifest_extra,
            }
            (temporary / f"{object_name}.json").write_text(
                json.dumps(
                    snapshot.payload_without_id(),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            try:
                temporary.rename(directory)
                directory_created = True
            except OSError:
                if not directory.exists():
                    raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    pointer = root / f"latest_{object_name}.json"
    pointer_before = _optional_bytes(pointer)
    pointer_after = json.dumps(
        {
            "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
            "object_type": object_name,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_path": str(directory),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    pointer_temp = root / f".{pointer.name}.{os.getpid()}.owned.tmp"
    pointer_temp.write_bytes(pointer_after)
    try:
        if pointer_before is None:
            try:
                os.link(pointer_temp, pointer)
            except FileExistsError:
                # A concurrent publisher won the absent-pointer race; do not overwrite it.
                pass
        else:
            pointer_temp.replace(pointer)
    finally:
        pointer_temp.unlink(missing_ok=True)
    if pointer.exists() and pointer.read_bytes() == pointer_after:
        stat = pointer.stat()
        inode = stat.st_ino
        mtime_ns = stat.st_mtime_ns
        size = stat.st_size
    else:
        inode = -1
        mtime_ns = -1
        size = -1
    return _OwnedOpportunityPublication(
        root=root,
        directory=directory,
        directory_created=directory_created,
        root_created=root_created,
        pointer=pointer,
        pointer_before=pointer_before,
        pointer_after=pointer_after,
        pointer_inode=inode,
        pointer_mtime_ns=mtime_ns,
        pointer_size=size,
    )


def _pointer_version_is_current(publication: _OwnedOpportunityPublication) -> bool:
    if publication.pointer_inode < 0 or not publication.pointer.exists():
        return False
    if publication.pointer.is_symlink():
        return False
    try:
        stat = publication.pointer.stat()
        return bool(
            stat.st_ino == publication.pointer_inode
            and stat.st_mtime_ns == publication.pointer_mtime_ns
            and stat.st_size == publication.pointer_size
            and publication.pointer.read_bytes() == publication.pointer_after
        )
    except OSError:
        return False


def _rollback_owned_opportunity_publication(
    publication: _OwnedOpportunityPublication,
    cleanup_errors: list[BaseException],
) -> None:
    # Never restore an older pointer over a possibly newer concurrent publisher. If a pointer
    # existed before this transaction, preserve this valid immutable publication on failure.
    if publication.pointer_before is not None:
        return
    # If another publisher has changed/replaced the pointer, ownership is no longer exclusive;
    # preserve both the pointer and immutable directory rather than deleting foreign state.
    if not _pointer_version_is_current(publication):
        return
    try:
        publication.pointer.unlink(missing_ok=True)
    except BaseException as exc:
        cleanup_errors.append(exc)
        return
    if publication.directory_created:
        try:
            if publication.directory.is_symlink():
                raise RuntimeError(
                    f"rollback refused symlinked snapshot directory: {publication.directory}"
                )
            if publication.directory.exists():
                shutil.rmtree(publication.directory)
        except BaseException as exc:
            cleanup_errors.append(exc)
            return
    if publication.root_created:
        try:
            publication.root.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            pass


'''
replace_between(
    assembler,
    "def _publish_orchestrated_artifacts(\n",
    "def _require_safe_run_ledger_publication(\n",
    new_publish,
)

# Happy-path fixtures now persist the preregistered Decision View selection rule.
replace_once(
    assembler_test,
    "    DecisionExpectationGapSnapshot,\n    DecisionViewSnapshot,\n    PriceImpliedGapObservation,\n    persist_decision_expectation_gap,\n    persist_decision_view,\n",
    "    DecisionExpectationGapSnapshot,\n    DecisionViewSnapshot,\n    PriceImpliedGapObservation,\n    build_decision_view_selection_rule,\n    persist_decision_expectation_gap,\n    persist_decision_view,\n    persist_decision_view_selection_rule,\n",
)
replace_once(
    assembler_test,
    "    payoff = PayoffSurfaceSnapshot(\n",
    "    selection_rule = build_decision_view_selection_rule(\n        rule_id=f\"fixture-selection-{security_id}\",\n        registered_at=NOW - timedelta(hours=4),\n        security_id=security_id,\n        target_variable=\"net_income\",\n        target_date=TARGET,\n        unit=\"KRW_million\",\n        selected_forecaster_kind=selected_registration.forecaster_kind,\n        selected_model_family=selected_registration.model_family,\n        rationale=\"Freeze forecaster identity before forecast registration.\",\n        source_evidence_ids=(A,),\n    )\n    payoff = PayoffSurfaceSnapshot(\n",
)
replace_once(
    assembler_test,
    "        selection_rule_snapshot_id=C,\n",
    "        selection_rule_snapshot_id=selection_rule.snapshot_id,\n",
)
replace_once(
    assembler_test,
    "        (selected_registration, benchmark_registration),\n    )\n",
    "        (selected_registration, benchmark_registration),\n        selection_rule,\n    )\n",
)
replace_once(
    assembler_test,
    "        payoff, view, gap, underwriting, registrations = _components(thesis, index)\n",
    "        payoff, view, gap, underwriting, registrations, selection_rule = _components(\n            thesis, index\n        )\n",
)
replace_once(
    assembler_test,
    "        for registration in registrations:\n            persist_forecast_registration(registration, output_root=tmp_path)\n",
    "        persist_decision_view_selection_rule(selection_rule, output_root=tmp_path)\n        for registration in registrations:\n            persist_forecast_registration(registration, output_root=tmp_path)\n",
)

# Regression: stale ready-preflight thesis identity must be persisted as a package blocker.
assembler_append = '''

def test_missing_preflight_selected_thesis_persists_current_package_blocker(
    tmp_path: Path,
) -> None:
    theses = _prepare_ready_request(tmp_path)
    missing = theses[0]
    (tmp_path / "investment_thesis_v2_1" / f"{missing.snapshot_id}.json").unlink()

    receipt = assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-stale-preflight-thesis",
        run_id="package-stale-preflight-thesis",
        processed_at=NOW + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.orchestrated is None
    assert receipt.run is not None
    assert receipt.run.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED
    codes = {item.code for item in receipt.blockers}
    assert "investment_thesis_snapshot_missing" in codes
    assert "preflight_thesis_identity_mismatch" in codes
    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert {row.state for row in state.inbox} == {"pre_orchestration_blocked"}
'''
Path(assembler_test).write_text(
    Path(assembler_test).read_text(encoding="utf-8") + assembler_append,
    encoding="utf-8",
)

# Focused canonical registration + selection-rule regressions.
replace_once(
    final_test,
    "from alpha_cycle.intelligence.forecast_ledger import (\n",
    "from alpha_cycle.intelligence.decision_view_v2_1 import (\n    build_decision_view_selection_rule,\n    persist_decision_view_selection_rule,\n)\nfrom alpha_cycle.intelligence.forecast_ledger import (\n",
)
final_append = '''

def test_fabricated_registration_payload_cannot_enter_persisted_tournament(
    tmp_path: Path,
) -> None:
    first = _registration(
        "forecast-a", model_family="model-a", cluster="a", value=20.0
    )
    second = _registration(
        "forecast-b", model_family="model-b", cluster="b", value=19.0
    )
    rule = build_decision_view_selection_rule(
        rule_id="canonical-rule",
        registered_at=NOW - timedelta(hours=4),
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        selected_forecaster_kind=first.forecaster_kind,
        selected_model_family=first.model_family,
        rationale="Pinned before forecast registration.",
        source_evidence_ids=(A,),
    )
    persist_decision_view_selection_rule(rule, output_root=tmp_path)
    persist_forecast_registration(first, output_root=tmp_path)
    pointer = persist_forecast_registration(second, output_root=tmp_path)
    pointer_payload = __import__("json").loads(pointer.read_text(encoding="utf-8"))
    directory = Path(pointer_payload["snapshot_path"])
    payload_path = directory / "forecast_registration.json"
    payload = __import__("json").loads(payload_path.read_text(encoding="utf-8"))
    payload["forecaster_kind"] = "fabricated-kind"
    payload["outcome_observed"] = True
    # Rebind the directory/manifest to the fabricated payload so simple hash/manifest checks pass.
    import hashlib
    import json

    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    fabricated_id = hashlib.sha256(encoded).hexdigest()
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["snapshot_id"] = fabricated_id
    manifest["forecast_id"] = second.forecast_id
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    new_directory = directory.with_name(directory.name.rsplit("__", 1)[0] + f"__{fabricated_id[:12]}")
    directory.rename(new_directory)

    view = _view(first, second)
    view.selection_rule_snapshot_id = rule.snapshot_id
    view.tournament_forecast_snapshot_ids = (first.snapshot_id, fabricated_id)
    tournament = _tournament(first, second)
    tournament.forecast_snapshot_ids = (first.snapshot_id, fabricated_id)
    underwriting = SimpleNamespace(
        forecast_tournament=tournament,
        guardrail_evidence_id=GUARDRAIL,
    )
    assert (
        decision_view_matches_underwriting_tournament(
            view, underwriting, artifact_root=tmp_path
        )
        is False
    )


def test_persisted_selection_rule_must_precede_and_uniquely_pin_forecast(
    tmp_path: Path,
) -> None:
    first = _registration(
        "forecast-a", model_family="model-a", cluster="a", value=20.0
    )
    second = _registration(
        "forecast-b", model_family="model-b", cluster="b", value=19.0
    )
    late_rule = build_decision_view_selection_rule(
        rule_id="late-rule",
        registered_at=first.registered_at + timedelta(minutes=1),
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        selected_forecaster_kind=first.forecaster_kind,
        selected_model_family=first.model_family,
        rationale="This rule is intentionally too late.",
        source_evidence_ids=(A,),
    )
    persist_decision_view_selection_rule(late_rule, output_root=tmp_path)
    persist_forecast_registration(first, output_root=tmp_path)
    persist_forecast_registration(second, output_root=tmp_path)
    view = _view(first, second)
    view.selection_rule_snapshot_id = late_rule.snapshot_id
    underwriting = SimpleNamespace(
        forecast_tournament=_tournament(first, second),
        guardrail_evidence_id=GUARDRAIL,
    )
    assert (
        decision_view_matches_underwriting_tournament(
            view, underwriting, artifact_root=tmp_path
        )
        is False
    )
'''
Path(final_test).write_text(
    Path(final_test).read_text(encoding="utf-8") + final_append,
    encoding="utf-8",
)
