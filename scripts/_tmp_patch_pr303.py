from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Harden persisted package integrity.
integrity = "src/alpha_cycle/research_package_integrity_v2_1.py"
replace_once(
    integrity,
    "from datetime import datetime\n",
    "from datetime import UTC, date, datetime\n",
)
replace_once(
    integrity,
    "from alpha_cycle.intelligence.opportunity_set_v2_1 import (\n",
    "from alpha_cycle.intelligence.forecast_ledger import (\n"
    "    FORECAST_LEDGER_SCHEMA_VERSION,\n"
    "    ForecastRegistrationMode,\n"
    ")\n"
    "from alpha_cycle.intelligence.opportunity_set_v2_1 import (\n",
)
replace_once(
    integrity,
    "    if lexical != resolved:\n"
    "        raise ResearchPackageIntegrityError(\n"
    "            \"artifact_root cannot traverse a symlinked path component\"\n"
    "        )\n"
    "    return resolved\n\n\n"
    "def validate_thesis_repository_layout(root: Path) -> None:\n",
    "    if lexical != resolved:\n"
    "        raise ResearchPackageIntegrityError(\n"
    "            \"artifact_root cannot traverse a symlinked path component\"\n"
    "        )\n"
    "    _validate_source_ledger_repository(root, resolved_root=resolved)\n"
    "    return resolved\n\n\n"
    "def _validate_source_ledger_repository(root: Path, *, resolved_root: Path) -> None:\n"
    "    repository = root / \"research_run_ledger_v2_1\"\n"
    "    if repository.is_symlink():\n"
    "        raise ResearchPackageIntegrityError(\n"
    "            \"research_run_ledger_v2_1 repository cannot be a symlink\"\n"
    "        )\n"
    "    if not repository.exists():\n"
    "        return\n"
    "    if not repository.is_dir():\n"
    "        raise ResearchPackageIntegrityError(\n"
    "            \"research_run_ledger_v2_1 repository must be a directory\"\n"
    "        )\n"
    "    resolved_repository = repository.resolve()\n"
    "    if resolved_repository.parent != resolved_root:\n"
    "        raise ResearchPackageIntegrityError(\n"
    "            \"research_run_ledger_v2_1 repository escapes artifact_root\"\n"
    "        )\n"
    "    for path in sorted(repository.glob(\"*.json\")):\n"
    "        if path.is_symlink():\n"
    "            raise ResearchPackageIntegrityError(\n"
    "                \"research run ledger artifact cannot be a symlink\"\n"
    "            )\n"
    "        if not path.is_file():\n"
    "            raise ResearchPackageIntegrityError(\n"
    "                \"research run ledger artifact must be a regular file\"\n"
    "            )\n"
    "        try:\n"
    "            resolved_path = path.resolve(strict=True)\n"
    "        except OSError as exc:\n"
    "            raise ResearchPackageIntegrityError(\n"
    "                f\"cannot resolve research run ledger artifact: {path}\"\n"
    "            ) from exc\n"
    "        if resolved_path.parent != resolved_repository:\n"
    "            raise ResearchPackageIntegrityError(\n"
    "                \"research run ledger artifact escapes repository root\"\n"
    "            )\n\n\n"
    "def validate_thesis_repository_layout(root: Path) -> None:\n",
)

old_matcher = '''def decision_view_matches_underwriting_tournament(
    view: DecisionViewSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
) -> bool:
    """Bind a Decision View to a genuine, exact parallel forecast tournament identity."""

    tournament = underwriting.forecast_tournament
    snapshot_ids = tuple(tournament.forecast_snapshot_ids)
    forecast_ids = tuple(tournament.forecast_ids)
    if len(snapshot_ids) != len(forecast_ids) or len(snapshot_ids) < 2:
        return False
    if len(set(snapshot_ids)) != len(snapshot_ids):
        return False
    if len(set(forecast_ids)) != len(forecast_ids):
        return False
    if not (2 <= tournament.distinct_forecaster_count <= len(snapshot_ids)):
        return False
    if not (1 <= tournament.dependency_cluster_count <= len(snapshot_ids)):
        return False
    if tournament.primary_error_metric is None:
        return False
    if tournament.information_cutoff is None:
        return False
    if tournament.information_cutoff > view.captured_at:
        return False
    if view.information_cutoff > view.captured_at:
        return False
    selected_pair = (view.selected_forecast_snapshot_id, view.selected_forecast_id)
    tournament_pairs = tuple(zip(snapshot_ids, forecast_ids, strict=True))
    return bool(
        tournament.comparable
        and not tournament.blockers
        and tournament.security_id == view.security_id
        and tournament.target_variable == view.target_variable
        and tournament.target_date == view.target_date
        and tournament.unit == view.unit
        and tournament.forecast_origin == view.forecast_origin
        and tournament.information_cutoff == view.information_cutoff
        and tuple(sorted(snapshot_ids))
        == tuple(sorted(view.tournament_forecast_snapshot_ids))
        and selected_pair in tournament_pairs
    )
'''
new_matcher = '''def decision_view_matches_underwriting_tournament(
    view: DecisionViewSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    *,
    artifact_root: str | Path | None = None,
) -> bool:
    """Bind a Decision View to a genuine persisted forecast tournament identity."""

    tournament = underwriting.forecast_tournament
    snapshot_ids = tuple(tournament.forecast_snapshot_ids)
    forecast_ids = tuple(tournament.forecast_ids)
    if len(snapshot_ids) != len(forecast_ids) or len(snapshot_ids) < 2:
        return False
    if len(set(snapshot_ids)) != len(snapshot_ids):
        return False
    if len(set(forecast_ids)) != len(forecast_ids):
        return False
    if not (2 <= tournament.distinct_forecaster_count <= len(snapshot_ids)):
        return False
    if not (1 <= tournament.dependency_cluster_count <= len(snapshot_ids)):
        return False
    if tournament.primary_error_metric is None:
        return False
    if tournament.information_cutoff is None or tournament.forecast_origin is None:
        return False
    if tournament.target_date is None:
        return False
    if tournament.information_cutoff > tournament.forecast_origin:
        return False
    if tournament.forecast_origin.date() >= tournament.target_date:
        return False
    if tournament.information_cutoff > view.captured_at:
        return False
    if view.information_cutoff > view.forecast_origin:
        return False
    if view.information_cutoff > view.captured_at:
        return False
    if view.forecast_origin.date() >= view.target_date:
        return False
    selected_pair = (view.selected_forecast_snapshot_id, view.selected_forecast_id)
    tournament_pairs = tuple(zip(snapshot_ids, forecast_ids, strict=True))
    base_match = bool(
        tournament.comparable
        and not tournament.blockers
        and tournament.security_id == view.security_id
        and tournament.target_variable == view.target_variable
        and tournament.target_date == view.target_date
        and tournament.unit == view.unit
        and tournament.forecast_origin == view.forecast_origin
        and tournament.information_cutoff == view.information_cutoff
        and tuple(sorted(snapshot_ids))
        == tuple(sorted(view.tournament_forecast_snapshot_ids))
        and selected_pair in tournament_pairs
    )
    if not base_match:
        return False
    if artifact_root is None:
        return True
    return _persisted_tournament_registrations_match(
        Path(artifact_root),
        view=view,
        underwriting=underwriting,
        snapshot_ids=snapshot_ids,
        forecast_ids=forecast_ids,
    )


def _persisted_tournament_registrations_match(
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
    descriptors: set[tuple[str, str]] = set()
    clusters: set[str] = set()
    tournament = underwriting.forecast_tournament
    for payload, expected_snapshot_id, expected_forecast_id in zip(
        registrations,
        snapshot_ids,
        forecast_ids,
        strict=True,
    ):
        if _sha(payload) != expected_snapshot_id:
            return False
        if payload.get("forecast_id") != expected_forecast_id:
            return False
        if payload.get("security_id") != view.security_id:
            return False
        if payload.get("target_variable") != view.target_variable:
            return False
        if payload.get("target_date") != view.target_date.isoformat():
            return False
        if payload.get("unit") != view.unit:
            return False
        if payload.get("primary_error_metric") != tournament.primary_error_metric:
            return False
        if payload.get("guardrail_evidence_id") != underwriting.guardrail_evidence_id:
            return False
        try:
            information_cutoff = _payload_datetime(payload, "information_cutoff")
            registered_at = _payload_datetime(payload, "registered_at")
            ledger_recorded_at = _payload_datetime(payload, "ledger_recorded_at")
            forecast_origin = _payload_datetime(payload, "forecast_origin")
            target_date = date.fromisoformat(str(payload.get("target_date")))
        except (TypeError, ValueError):
            return False
        if not (
            information_cutoff <= registered_at <= ledger_recorded_at
            and registered_at <= forecast_origin
            and information_cutoff == view.information_cutoff
            and forecast_origin == view.forecast_origin
            and target_date == view.target_date
            and forecast_origin.date() < target_date
            and ledger_recorded_at <= view.captured_at
        ):
            return False
        if (
            payload.get("registration_mode")
            == ForecastRegistrationMode.NATIVE_PROSPECTIVE.value
            and ledger_recorded_at > forecast_origin
        ):
            return False
        forecaster_kind = payload.get("forecaster_kind")
        model_family = payload.get("model_family")
        dependency_cluster = payload.get("dependency_cluster_id")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (forecaster_kind, model_family, dependency_cluster)
        ):
            return False
        descriptors.add((str(forecaster_kind), str(model_family)))
        clusters.add(str(dependency_cluster))

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
    if selected.get("forecast_id") != view.selected_forecast_id:
        return False
    if selected.get("forecaster_kind") != view.selected_forecaster_kind.value:
        return False
    if selected.get("model_family") != view.selected_model_family:
        return False
    selected_value = selected.get("forecast_value")
    if not isinstance(selected_value, (int, float)) or isinstance(selected_value, bool):
        return False
    return _numbers_match(float(selected_value), view.selected_forecast_value)


def _load_persisted_forecast_registrations(
    root: Path,
    snapshot_ids: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    resolved_root = require_trusted_artifact_root(root)
    repository = root / "registration"
    _require_safe_repository(
        repository,
        resolved_root=resolved_root,
        label="forecast registration",
    )
    if not repository.exists():
        return ()
    loaded: list[dict[str, object]] = []
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
        if _sha(payload) != snapshot_id:
            return ()
        try:
            ledger_recorded_at = _payload_datetime(payload, "ledger_recorded_at")
        except ValueError:
            return ()
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
            "forecast_id": payload.get("forecast_id"),
            "registration_mode": payload.get("registration_mode"),
            "dependency_cluster_id": payload.get("dependency_cluster_id"),
            "guardrail_evidence_id": payload.get("guardrail_evidence_id"),
            "outcome_observed": False,
            "evaluation_run": False,
        }
        if manifest != expected_manifest:
            return ()
        loaded.append(payload)
    return tuple(loaded)


def _payload_datetime(payload: dict[str, object], field: str) -> datetime:
    raw = payload.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} must be non-empty text")
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value
'''
replace_once(integrity, old_matcher, new_matcher)
replace_once(
    integrity,
    "    if underwriting is not None and not _underwriting_ready_contract_is_valid(underwriting):\n",
    "    if underwriting is not None and not _underwriting_ready_contract_is_valid(\n"
    "        thesis, underwriting, payoff\n"
    "    ):\n",
)
old_contract = '''def _underwriting_ready_contract_is_valid(
    underwriting: UnderwritingReadinessSnapshot,
) -> bool:
    if underwriting.readiness not in _READY_UNDERWRITING_STATES:
        return True
    active = load_decision_system_v21_guardrails()
    if underwriting.lane is UnderwritingLane.FAST:
        if underwriting.readiness is not UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW:
            return False
        required = tuple(active.fast_lane_required_elements)
    elif underwriting.lane is UnderwritingLane.DEEP:
        if underwriting.readiness not in {
            UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW,
            UnderwritingReadiness.DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS,
        }:
            return False
        required = tuple(active.deep_lane_required_elements) + SUPPLEMENTAL_DEEP_ELEMENTS
    else:
        return False
    return bool(
        tuple(underwriting.required_elements_satisfied) == required
        and not underwriting.required_elements_missing
        and not underwriting.blockers
    )
'''
new_contract = '''def _underwriting_ready_contract_is_valid(
    thesis: InvestmentThesisSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    payoff: PayoffSurfaceSnapshot | None,
) -> bool:
    if underwriting.readiness not in _READY_UNDERWRITING_STATES:
        return True
    active = load_decision_system_v21_guardrails()
    if underwriting.lane is UnderwritingLane.FAST:
        if underwriting.readiness is not UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW:
            return False
        required = tuple(active.fast_lane_required_elements)
        return bool(
            tuple(underwriting.required_elements_satisfied) == required
            and not underwriting.required_elements_missing
            and not underwriting.blockers
        )
    if underwriting.lane is not UnderwritingLane.DEEP:
        return False
    required = tuple(active.deep_lane_required_elements) + SUPPLEMENTAL_DEEP_ELEMENTS
    if tuple(underwriting.required_elements_satisfied) != required:
        return False
    if underwriting.required_elements_missing or underwriting.blockers:
        return False
    if underwriting.flags:
        if underwriting.readiness is not UnderwritingReadiness.DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS:
            return False
    elif underwriting.readiness is not UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW:
        return False
    required_snapshot_ids = (
        underwriting.causal_graph_snapshot_id,
        underwriting.expectation_state_snapshot_id,
        underwriting.forward_valuation_snapshot_id,
        underwriting.price_implied_requirement_snapshot_id,
        underwriting.payoff_surface_snapshot_id,
        underwriting.epistemic_defense_snapshot_id,
    )
    if any(value is None for value in required_snapshot_ids):
        return False
    if payoff is None or underwriting.payoff_surface_snapshot_id != payoff.snapshot_id:
        return False
    if not thesis.catalysts or not thesis.kill_conditions:
        return False
    if not thesis.opportunity_set_refs or not thesis.portfolio_overlap:
        return False
    if not underwriting.forecast_tournament.comparable:
        return False
    if not set(underwriting.forecast_tournament.flags).issubset(set(underwriting.flags)):
        return False
    return True
'''
replace_once(integrity, old_contract, new_contract)

# 2) Make the assembler consume the strict persisted tournament proof.
assembler = "src/alpha_cycle/research_package_assembler_v2_1.py"
replace_once(
    assembler,
    "                component_index=component_index,\n"
    "                guardrail_evidence_id=active.evidence_id,\n",
    "                component_index=component_index,\n"
    "                guardrail_evidence_id=active.evidence_id,\n"
    "                artifact_root=root,\n",
)
replace_once(
    assembler,
    "    guardrail_evidence_id: str,\n"
    "    blockers: list[ResearchRoundBlocker],\n",
    "    guardrail_evidence_id: str,\n"
    "    artifact_root: Path,\n"
    "    blockers: list[ResearchRoundBlocker],\n",
)
replace_once(
    assembler,
    "        if not decision_view_matches_underwriting_tournament(view, underwriting):\n",
    "        if not decision_view_matches_underwriting_tournament(\n"
    "            view, underwriting, artifact_root=artifact_root\n"
    "        ):\n",
)

# 3) Fix research-round O_EXCL cleanup so it only removes a file this writer created.
orchestrator = "src/alpha_cycle/intelligence/research_round_orchestrator_v2_1.py"
replace_once(
    orchestrator,
    "    fd: int | None = None\n"
    "    try:\n"
    "        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)\n",
    "    fd: int | None = None\n"
    "    created = False\n"
    "    try:\n"
    "        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)\n"
    "        created = True\n",
)
replace_once(
    orchestrator,
    "    except BaseException:\n"
    "        if fd is not None:\n"
    "            os.close(fd)\n"
    "        path.unlink(missing_ok=True)\n"
    "        raise\n"
    "    return path\n",
    "    except BaseException:\n"
    "        if fd is not None:\n"
    "            os.close(fd)\n"
    "        if created:\n"
    "            path.unlink(missing_ok=True)\n"
    "        raise\n"
    "    return path\n",
)

# 4) Update the end-to-end assembler fixture to persist genuine forecast registrations
# and carry the concrete Deep-lane evidence bindings it claims.
assembler_test = "tests/unit/test_research_package_assembler_v2_1.py"
replace_once(
    assembler_test,
    "from alpha_cycle.intelligence.decision_view_v2_1 import (\n"
    "    ConsensusGapObservation,\n"
    "    DecisionExpectationGapSnapshot,\n"
    "    DecisionViewSnapshot,\n",
    "from alpha_cycle.intelligence.decision_view_v2_1 import (\n"
    "    ConsensusGapObservation,\n"
    "    DecisionExpectationGapSnapshot,\n"
    "    DecisionViewSnapshot,\n"
    "    PriceImpliedGapObservation,\n",
)
replace_once(
    assembler_test,
    "from alpha_cycle.intelligence.forecast_ledger import ForecasterKind\n",
    "from alpha_cycle.intelligence.forecast_ledger import (\n"
    "    ForecasterKind,\n"
    "    ForecastRegistrationMode,\n"
    "    ForecastRegistrationSnapshot,\n"
    "    OrdinalAssessment,\n"
    "    PrimaryErrorMetric,\n"
    "    persist_forecast_registration,\n"
    ")\n",
)
replace_once(
    assembler_test,
    "F = \"f\" * 64\n\n\n",
    "F = \"f\" * 64\n"
    "CAUSAL_GRAPH_ID = \"1\" * 64\n"
    "FORWARD_VALUATION_ID = \"2\" * 64\n"
    "PRICE_IMPLIED_ID = \"3\" * 64\n"
    "EPISTEMIC_DEFENSE_ID = \"4\" * 64\n\n\n",
)
insert_registration = '''def _registration(
    thesis: InvestmentThesisSnapshot,
    *,
    forecast_id: str,
    model_family: str,
    forecaster_kind: ForecasterKind,
    dependency_cluster_id: str,
    forecast_value: float,
) -> ForecastRegistrationSnapshot:
    return ForecastRegistrationSnapshot(
        forecast_id=forecast_id,
        registered_at=NOW - timedelta(hours=2, minutes=30),
        ledger_recorded_at=NOW - timedelta(hours=2, minutes=20),
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        security_id=thesis.security_id,
        target_variable="net_income",
        target_date=TARGET,
        horizon_label="fixture-forward-target",
        forecast_value=forecast_value,
        unit="KRW_million",
        range_lower=None,
        range_upper=None,
        direction=None,
        direction_reference_value=None,
        direction_flat_tolerance=0.0,
        confidence=OrdinalAssessment.MEDIUM,
        confidence_rationale="Persisted package fixture forecast.",
        forecaster_kind=forecaster_kind,
        model_family=model_family,
        driver_refs=("driver:fixture",),
        regime_tags=("fixture-regime",),
        decision_relevance=OrdinalAssessment.HIGH,
        difficulty=OrdinalAssessment.MEDIUM,
        baseline_refs=(),
        dependency_cluster_id=dependency_cluster_id,
        source_evidence_ids=(A,),
        registration_mode=ForecastRegistrationMode.NATIVE_PROSPECTIVE,
        primary_error_metric=PrimaryErrorMetric.ABSOLUTE_ERROR,
        guardrail_evidence_id=GUARDRAIL,
    )


'''
replace_once(
    assembler_test,
    "def _components(thesis: InvestmentThesisSnapshot, offset: int):\n",
    insert_registration + "def _components(thesis: InvestmentThesisSnapshot, offset: int):\n",
)
replace_once(
    assembler_test,
    "    security_id = thesis.security_id\n"
    "    payoff = PayoffSurfaceSnapshot(\n",
    "    security_id = thesis.security_id\n"
    "    selected_registration = _registration(\n"
    "        thesis,\n"
    "        forecast_id=f\"a-{security_id}\",\n"
    "        model_family=\"fixture-model\",\n"
    "        forecaster_kind=ForecasterKind.MODEL,\n"
    "        dependency_cluster_id=f\"model-{security_id}\",\n"
    "        forecast_value=20_000_000.0 + offset,\n"
    "    )\n"
    "    benchmark_registration = _registration(\n"
    "        thesis,\n"
    "        forecast_id=f\"b-{security_id}\",\n"
    "        model_family=\"fixture-benchmark\",\n"
    "        forecaster_kind=ForecasterKind.BENCHMARK,\n"
    "        dependency_cluster_id=f\"benchmark-{security_id}\",\n"
    "        forecast_value=18_000_000.0 + offset,\n"
    "    )\n"
    "    payoff = PayoffSurfaceSnapshot(\n",
)
replace_once(
    assembler_test,
    "        selected_forecast_snapshot_id=D,\n"
    "        selected_forecast_id=f\"a-{security_id}\",\n"
    "        selected_forecaster_kind=ForecasterKind.MODEL,\n"
    "        selected_model_family=\"fixture-model\",\n"
    "        selected_forecast_value=20_000_000.0 + offset,\n",
    "        selected_forecast_snapshot_id=selected_registration.snapshot_id,\n"
    "        selected_forecast_id=selected_registration.forecast_id,\n"
    "        selected_forecaster_kind=selected_registration.forecaster_kind,\n"
    "        selected_model_family=selected_registration.model_family,\n"
    "        selected_forecast_value=selected_registration.forecast_value,\n",
)
replace_once(
    assembler_test,
    "        tournament_forecast_snapshot_ids=(D, E),\n",
    "        tournament_forecast_snapshot_ids=(\n"
    "            selected_registration.snapshot_id,\n"
    "            benchmark_registration.snapshot_id,\n"
    "        ),\n",
)
replace_once(
    assembler_test,
    "        price_implied_requirement_snapshot_id=None,\n"
    "        security_id=security_id,\n",
    "        price_implied_requirement_snapshot_id=PRICE_IMPLIED_ID,\n"
    "        security_id=security_id,\n",
)
replace_once(
    assembler_test,
    "        price_implied_gaps=(),\n"
    "        flags=(\"price_implied_comparison_not_supplied\",),\n",
    "        price_implied_gaps=(\n"
    "            PriceImpliedGapObservation(\n"
    "                reference_id=\"fixture-price-reference\",\n"
    "                reference_kind=\"forward_multiple\",\n"
    "                reference_multiple=10.0,\n"
    "                decision_value_krw=view.selected_forecast_value * 1_000_000.0,\n"
    "                implied_value_krw=18_000_000.0 * 1_000_000.0,\n"
    "                absolute_gap_krw=(\n"
    "                    view.selected_forecast_value - 18_000_000.0\n"
    "                ) * 1_000_000.0,\n"
    "                relative_gap=(\n"
    "                    view.selected_forecast_value - 18_000_000.0\n"
    "                ) / 18_000_000.0,\n"
    "            ),\n"
    "        ),\n"
    "        flags=(),\n",
)
replace_once(
    assembler_test,
    "        forecast_snapshot_ids=(D, E),\n"
    "        forecast_ids=(f\"a-{security_id}\", f\"b-{security_id}\"),\n",
    "        forecast_snapshot_ids=(\n"
    "            selected_registration.snapshot_id,\n"
    "            benchmark_registration.snapshot_id,\n"
    "        ),\n"
    "        forecast_ids=(\n"
    "            selected_registration.forecast_id,\n"
    "            benchmark_registration.forecast_id,\n"
    "        ),\n",
)
replace_once(
    assembler_test,
    "        causal_graph_snapshot_id=None,\n",
    "        causal_graph_snapshot_id=CAUSAL_GRAPH_ID,\n",
)
replace_once(
    assembler_test,
    "        forward_valuation_snapshot_id=None,\n"
    "        price_implied_requirement_snapshot_id=None,\n"
    "        payoff_surface_snapshot_id=payoff.snapshot_id,\n"
    "        epistemic_defense_snapshot_id=None,\n",
    "        forward_valuation_snapshot_id=FORWARD_VALUATION_ID,\n"
    "        price_implied_requirement_snapshot_id=PRICE_IMPLIED_ID,\n"
    "        payoff_surface_snapshot_id=payoff.snapshot_id,\n"
    "        epistemic_defense_snapshot_id=EPISTEMIC_DEFENSE_ID,\n",
)
replace_once(
    assembler_test,
    "    return payoff, view, gap, underwriting\n",
    "    return (\n"
    "        payoff,\n"
    "        view,\n"
    "        gap,\n"
    "        underwriting,\n"
    "        (selected_registration, benchmark_registration),\n"
    "    )\n",
)
replace_once(
    assembler_test,
    "        payoff, view, gap, underwriting = _components(thesis, index)\n",
    "        payoff, view, gap, underwriting, registrations = _components(thesis, index)\n",
)
replace_once(
    assembler_test,
    "        persist_payoff_surface(payoff, output_root=tmp_path / \"payoff_surface\")\n",
    "        for registration in registrations:\n"
    "            persist_forecast_registration(registration, output_root=tmp_path)\n"
    "        persist_payoff_surface(payoff, output_root=tmp_path / \"payoff_surface\")\n",
)

# 5) Add focused regressions for the six final findings.
new_test = Path("tests/unit/test_research_package_codex_final_gate_v2_1.py")
if new_test.exists():
    raise SystemExit(f"unexpected existing file: {new_test}")
new_test.write_text('''from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.forecast_ledger import (
    ForecasterKind,
    ForecastRegistrationMode,
    ForecastRegistrationSnapshot,
    OrdinalAssessment,
    PrimaryErrorMetric,
    persist_forecast_registration,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    persist_research_round,
)
from alpha_cycle.intelligence.underwriter_v2_1 import (
    SUPPLEMENTAL_DEEP_ELEMENTS,
    UnderwritingLane,
    UnderwritingReadiness,
)
from alpha_cycle.research_package_integrity_v2_1 import (
    ResearchPackageIntegrityError,
    decision_view_matches_underwriting_tournament,
    package_integrity_blocker_codes,
    require_trusted_artifact_root,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
TARGET = date(2026, 12, 31)
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64
DEEP_REQUIRED = (
    load_decision_system_v21_guardrails().deep_lane_required_elements
    + SUPPLEMENTAL_DEEP_ELEMENTS
)


def _thesis() -> SimpleNamespace:
    return SimpleNamespace(
        status=SimpleNamespace(value="underwriting"),
        captured_at=NOW,
        catalysts=("earnings",),
        kill_conditions=("kill",),
        opportunity_set_refs=("opportunity",),
        portfolio_overlap=("cycle",),
    )


def _ready_underwriting(*, flags: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        captured_at=NOW,
        lane=UnderwritingLane.DEEP,
        readiness=UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW,
        required_elements_satisfied=DEEP_REQUIRED,
        required_elements_missing=(),
        blockers=(),
        flags=flags,
        causal_graph_snapshot_id=A,
        expectation_state_snapshot_id=B,
        forward_valuation_snapshot_id=C,
        price_implied_requirement_snapshot_id=D,
        payoff_surface_snapshot_id=E,
        epistemic_defense_snapshot_id=F,
        forecast_tournament=SimpleNamespace(comparable=True, flags=()),
    )


def _registration(
    forecast_id: str,
    *,
    model_family: str,
    cluster: str,
    value: float,
) -> ForecastRegistrationSnapshot:
    return ForecastRegistrationSnapshot(
        forecast_id=forecast_id,
        registered_at=NOW - timedelta(hours=2, minutes=30),
        ledger_recorded_at=NOW - timedelta(hours=2, minutes=20),
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        horizon_label="fixture",
        forecast_value=value,
        unit="KRW_million",
        range_lower=None,
        range_upper=None,
        direction=None,
        direction_reference_value=None,
        direction_flat_tolerance=0.0,
        confidence=OrdinalAssessment.MEDIUM,
        confidence_rationale="fixture",
        forecaster_kind=ForecasterKind.MODEL,
        model_family=model_family,
        driver_refs=("driver",),
        regime_tags=("regime",),
        decision_relevance=OrdinalAssessment.HIGH,
        difficulty=OrdinalAssessment.MEDIUM,
        baseline_refs=(),
        dependency_cluster_id=cluster,
        source_evidence_ids=(A,),
        registration_mode=ForecastRegistrationMode.NATIVE_PROSPECTIVE,
        primary_error_metric=PrimaryErrorMetric.ABSOLUTE_ERROR,
        guardrail_evidence_id=GUARDRAIL,
    )


def _view(first: ForecastRegistrationSnapshot, second: ForecastRegistrationSnapshot):
    return SimpleNamespace(
        captured_at=NOW,
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        forecast_origin=first.forecast_origin,
        information_cutoff=first.information_cutoff,
        tournament_forecast_snapshot_ids=(first.snapshot_id, second.snapshot_id),
        tournament_dependency_overlap=False,
        selected_forecast_snapshot_id=first.snapshot_id,
        selected_forecast_id=first.forecast_id,
        selected_forecaster_kind=first.forecaster_kind,
        selected_model_family=first.model_family,
        selected_forecast_value=first.forecast_value,
    )


def _tournament(first: ForecastRegistrationSnapshot, second: ForecastRegistrationSnapshot):
    return SimpleNamespace(
        comparable=True,
        forecast_snapshot_ids=(first.snapshot_id, second.snapshot_id),
        forecast_ids=(first.forecast_id, second.forecast_id),
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        forecast_origin=first.forecast_origin,
        information_cutoff=first.information_cutoff,
        primary_error_metric="absolute_error",
        distinct_forecaster_count=2,
        dependency_cluster_count=2,
        blockers=(),
        flags=(),
    )


def test_ready_deep_elements_require_concrete_bound_snapshot_ids() -> None:
    underwriting = _ready_underwriting()
    underwriting.causal_graph_snapshot_id = None
    payoff = SimpleNamespace(snapshot_id=E, captured_at=NOW)
    blockers = package_integrity_blocker_codes(
        _thesis(), underwriting, payoff, None, None
    )
    assert "underwriting_ready_evidence_contract_mismatch" in blockers


def test_deep_flags_require_flagged_readiness_state() -> None:
    underwriting = _ready_underwriting(flags=("counter_evidence_material",))
    payoff = SimpleNamespace(snapshot_id=E, captured_at=NOW)
    blockers = package_integrity_blocker_codes(
        _thesis(), underwriting, payoff, None, None
    )
    assert "underwriting_ready_evidence_contract_mismatch" in blockers


def test_persisted_tournament_must_prove_distinct_forecaster_descriptors(
    tmp_path: Path,
) -> None:
    first = _registration("forecast-a", model_family="same-model", cluster="a", value=20.0)
    second = _registration("forecast-b", model_family="same-model", cluster="b", value=19.0)
    persist_forecast_registration(first, output_root=tmp_path)
    persist_forecast_registration(second, output_root=tmp_path)
    view = _view(first, second)
    underwriting = SimpleNamespace(
        forecast_tournament=_tournament(first, second),
        guardrail_evidence_id=GUARDRAIL,
    )
    assert (
        decision_view_matches_underwriting_tournament(
            view,
            underwriting,
            artifact_root=tmp_path,
        )
        is False
    )


def test_persisted_tournament_rejects_impossible_chronology() -> None:
    first = _registration("forecast-a", model_family="model-a", cluster="a", value=20.0)
    second = _registration("forecast-b", model_family="model-b", cluster="b", value=19.0)
    view = _view(first, second)
    tournament = _tournament(first, second)
    future_cutoff = view.forecast_origin + timedelta(minutes=1)
    view.information_cutoff = future_cutoff
    tournament.information_cutoff = future_cutoff
    underwriting = SimpleNamespace(forecast_tournament=tournament)
    assert decision_view_matches_underwriting_tournament(view, underwriting) is False


def test_source_ledger_symlink_is_rejected_before_observatory_read(tmp_path: Path) -> None:
    ledger_root = tmp_path / "research_run_ledger_v2_1"
    ledger_root.mkdir()
    outside = tmp_path / "outside-ledger.json"
    outside.write_text("{}", encoding="utf-8")
    (ledger_root / f"{A}.json").symlink_to(outside)
    with pytest.raises(ResearchPackageIntegrityError, match="ledger artifact cannot be a symlink"):
        require_trusted_artifact_root(tmp_path)


def test_research_round_eexist_never_deletes_preexisting_artifact(tmp_path: Path) -> None:
    snapshot = SimpleNamespace(
        snapshot_id=A,
        payload_without_id=lambda: {"schema_version": 1, "round_id": "existing"},
    )
    path = tmp_path / "research_round_v2_1" / f"{A}.json"
    path.parent.mkdir(parents=True)
    original = b"pre-existing-round\n"
    path.write_bytes(original)
    with pytest.raises(FileExistsError):
        persist_research_round(snapshot, output_root=tmp_path)
    assert path.read_bytes() == original
''', encoding="utf-8")
