from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}: found {count}\n{old[:160]}")
    path.write_text(text.replace(old, new), encoding="utf-8")


root = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Clean the source-chain revalidation module added before this patch runner.
# ---------------------------------------------------------------------------
source = root / "src/alpha_cycle/research_package_source_revalidation_v2_1.py"
replace_once(source, "from datetime import date, datetime\n", "from datetime import UTC, date, datetime\n")
replace_once(
    source,
    "from alpha_cycle.intelligence.forward_valuation import (\n    ForwardValuationStateSnapshot,\n    build_forward_valuation_state,\n)\n",
    "from alpha_cycle.intelligence.forward_valuation import (\n    ForwardValuationMetric,\n    ForwardValuationStateSnapshot,\n    build_forward_valuation_state,\n)\n",
)
replace_once(
    source,
    "from alpha_cycle.intelligence.price_implied_requirement import (\n    PRICE_IMPLIED_SCHEMA_VERSION,\n    ReferenceFrameKind,\n    ValuationReferenceFrameSnapshot,\n    ValuationReferencePoint,\n    build_price_implied_requirement,\n)\n",
    "from alpha_cycle.intelligence.price_implied_requirement import (\n    PRICE_IMPLIED_SCHEMA_VERSION,\n    PriceImpliedRequirementSnapshot,\n    ReferenceFrameKind,\n    ValuationReferenceFrameSnapshot,\n    ValuationReferencePoint,\n    build_price_implied_requirement,\n)\n",
)
replace_once(
    source,
    '''def price_implied_sources_are_canonical(\n    root: str | Path,\n    *,\n    snapshot: object,\n) -> bool:\n    """Rebuild a price-implied requirement from valuation and reference-frame sources."""\n\n    from alpha_cycle.intelligence.price_implied_requirement import PriceImpliedRequirementSnapshot\n\n    if not isinstance(snapshot, PriceImpliedRequirementSnapshot):\n        return False\n''',
    '''def price_implied_sources_are_canonical(\n    root: str | Path,\n    *,\n    snapshot: PriceImpliedRequirementSnapshot,\n) -> bool:\n    """Rebuild a price-implied requirement from valuation and reference-frame sources."""\n''',
)
replace_once(
    source,
    '''    except (KeyError, OSError, TypeError, ValueError, pd.errors.ParserError):\n        return None\n''',
    '''    except (\n        KeyError,\n        OSError,\n        TypeError,\n        ValueError,\n        pd.errors.EmptyDataError,\n        pd.errors.ParserError,\n    ):\n        return None\n''',
)
replace_once(
    source,
    '''    expected_name = (\n        snapshot.captured_at.astimezone().astimezone(datetime.now().astimezone().tzinfo)\n    )\n    del expected_name\n    timestamp = snapshot.captured_at.astimezone(__import__("datetime").timezone.utc).strftime(\n        "%Y%m%dT%H%M%S%fZ"\n    )\n''',
    '''    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")\n''',
)
replace_once(
    source,
    '''def _forward_metric(value: str):\n    from alpha_cycle.intelligence.forward_valuation import ForwardValuationMetric\n\n    return ForwardValuationMetric(value)\n''',
    '''def _forward_metric(value: str) -> ForwardValuationMetric:\n    return ForwardValuationMetric(value)\n''',
)

# ---------------------------------------------------------------------------
# Make canonical package evidence traverse the complete source chain.
# Local import avoids a module-init cycle because the source validator itself
# reuses the shared trusted-root boundary from research_package_integrity_v2_1.
# ---------------------------------------------------------------------------
canonical = root / "src/alpha_cycle/research_package_canonical_evidence_v2_1.py"
replace_once(
    canonical,
    '''    artifact_root = Path(root)\n    active = load_decision_system_v21_guardrails()\n''',
    '''    from alpha_cycle.research_package_source_revalidation_v2_1 import (\n        epistemic_package_sources_are_canonical,\n        forward_valuation_sources_are_canonical,\n        price_implied_sources_are_canonical,\n    )\n\n    artifact_root = Path(root)\n    active = load_decision_system_v21_guardrails()\n''',
)
replace_once(
    canonical,
    '''        if (\n            forward_valuation.evaluation_date != underwriting.evaluation_date\n            or forward_valuation.expectation_state_snapshot_id != expectations.snapshot_id\n            or forward_valuation.guardrail_evidence_id\n            != underwriting.guardrail_evidence_id\n            or forward_valuation.captured_at > underwriting.captured_at\n        ):\n            return False\n''',
    '''        if (\n            forward_valuation.evaluation_date != underwriting.evaluation_date\n            or forward_valuation.expectation_state_snapshot_id != expectations.snapshot_id\n            or forward_valuation.guardrail_evidence_id\n            != underwriting.guardrail_evidence_id\n            or forward_valuation.captured_at > underwriting.captured_at\n        ):\n            return False\n        if not forward_valuation_sources_are_canonical(\n            artifact_root,\n            snapshot=forward_valuation,\n            expectations=expectations,\n        ):\n            return False\n''',
)
replace_once(
    canonical,
    '''    if price_implied is not None and (\n        price_implied.security_id != thesis.security_id\n        or price_implied.evaluation_date != underwriting.evaluation_date\n        or price_implied.guardrail_evidence_id != underwriting.guardrail_evidence_id\n        or price_implied.captured_at > underwriting.captured_at\n    ):\n        return False\n''',
    '''    if price_implied is not None and (\n        price_implied.security_id != thesis.security_id\n        or price_implied.evaluation_date != underwriting.evaluation_date\n        or price_implied.guardrail_evidence_id != underwriting.guardrail_evidence_id\n        or price_implied.captured_at > underwriting.captured_at\n    ):\n        return False\n    if price_implied is not None and not price_implied_sources_are_canonical(\n        artifact_root,\n        snapshot=price_implied,\n    ):\n        return False\n''',
)
replace_once(
    canonical,
    '''    if epistemic is not None and (\n        epistemic.thesis_snapshot_id != thesis.snapshot_id\n        or epistemic.guardrail_evidence_id != underwriting.guardrail_evidence_id\n        or epistemic.captured_at > underwriting.captured_at\n        or not epistemic.required_contracts_present\n    ):\n        return False\n''',
    '''    if epistemic is not None and (\n        epistemic.thesis_snapshot_id != thesis.snapshot_id\n        or epistemic.guardrail_evidence_id != underwriting.guardrail_evidence_id\n        or epistemic.captured_at > underwriting.captured_at\n        or not epistemic.required_contracts_present\n    ):\n        return False\n    if epistemic is not None and not epistemic_package_sources_are_canonical(\n        artifact_root,\n        thesis=thesis,\n        snapshot=epistemic,\n    ):\n        return False\n''',
)

# ---------------------------------------------------------------------------
# Remove check-then-rename and check-then-unlink TOCTOU windows.  The canonical
# name is atomically claimed into an unpredictable same-directory quarantine;
# verification happens on that stable claimed pathname.  A concurrent publisher
# may recreate the canonical name, in which case it wins and is never overwritten.
# ---------------------------------------------------------------------------
assembler = root / "src/alpha_cycle/research_package_assembler_v2_1.py"
old_replace = '''def _replace_pointer_if_version_matches(\n    replacement: Path,\n    pointer: Path,\n    *,\n    expected_bytes: bytes,\n    expected_identity: tuple[int, int, int],\n) -> bool:\n    """Replace a mutable pointer only when the version read by this writer is still current."""\n\n    if pointer.is_symlink() or not pointer.exists():\n        return False\n    try:\n        if _capture_file_identity(pointer) != expected_identity:\n            return False\n        if pointer.read_bytes() != expected_bytes:\n            return False\n        # Recheck immediately before publication so a replaced inode/version is never knowingly\n        # overwritten. Cooperative writers use this same CAS boundary; a foreign replacement\n        # observed at either check wins and is preserved.\n        if _capture_file_identity(pointer) != expected_identity:\n            return False\n        replacement.replace(pointer)\n        return True\n    except FileNotFoundError:\n        return False\n'''
new_replace = '''def _replace_pointer_if_version_matches(\n    replacement: Path,\n    pointer: Path,\n    *,\n    expected_bytes: bytes,\n    expected_identity: tuple[int, int, int],\n) -> bool:\n    """Conditionally publish without a check-then-rename race.\n\n    The current canonical name is first atomically claimed into an unpredictable\n    same-directory quarantine.  Verification then occurs on the stable claimed\n    pathname.  Publication uses a no-replace hard link, so a direct/non-cooperating\n    publisher that recreates the canonical name while we validate always wins.\n    """\n\n    if pointer.is_symlink() or not pointer.exists():\n        return False\n    quarantine = _new_publication_quarantine(pointer)\n    try:\n        try:\n            os.replace(pointer, quarantine)\n        except FileNotFoundError:\n            return False\n        if quarantine.is_symlink() or not quarantine.is_file():\n            return False\n        matches = bool(\n            _capture_file_identity(quarantine) == expected_identity\n            and quarantine.read_bytes() == expected_bytes\n        )\n        if not matches:\n            _restore_quarantined_file_if_absent(quarantine, pointer)\n            return False\n        try:\n            os.link(replacement, pointer)\n        except FileExistsError:\n            # A concurrent publisher recreated the canonical name after our claim.\n            return False\n        return True\n    finally:\n        quarantine.unlink(missing_ok=True)\n\n\ndef _new_publication_quarantine(path: Path) -> Path:\n    fd, name = tempfile.mkstemp(\n        prefix=f".{path.name}.",\n        suffix=".quarantine",\n        dir=path.parent,\n    )\n    os.close(fd)\n    return Path(name)\n\n\ndef _restore_quarantined_file_if_absent(quarantine: Path, destination: Path) -> bool:\n    if quarantine.is_symlink() or not quarantine.is_file():\n        return False\n    try:\n        os.link(quarantine, destination)\n        return True\n    except FileExistsError:\n        # A concurrent publisher owns the canonical name now.\n        return False\n\n\ndef _unlink_pointer_if_version_matches(\n    pointer: Path,\n    *,\n    expected_bytes: bytes,\n    expected_identity: tuple[int, int, int],\n) -> bool:\n    """Delete only the exact pointer version atomically claimed by this rollback."""\n\n    if pointer.is_symlink() or not pointer.exists():\n        return False\n    quarantine = _new_publication_quarantine(pointer)\n    try:\n        try:\n            os.replace(pointer, quarantine)\n        except FileNotFoundError:\n            return False\n        if quarantine.is_symlink() or not quarantine.is_file():\n            return False\n        matches = bool(\n            _capture_file_identity(quarantine) == expected_identity\n            and quarantine.read_bytes() == expected_bytes\n        )\n        if not matches:\n            _restore_quarantined_file_if_absent(quarantine, pointer)\n            return False\n        # The owned version is now isolated at the quarantine pathname.  If a\n        # concurrent publisher has recreated `pointer`, it is left untouched.\n        return True\n    finally:\n        quarantine.unlink(missing_ok=True)\n'''
replace_once(assembler, old_replace, new_replace)

old_rollback_pointer = '''    if publication.pointer_before is not None:\n        # Restore the previous pointer only while our own published version is still current.\n        # A concurrent replacement wins; we never overwrite foreign state during rollback.\n        if not _pointer_version_is_current(publication):\n            return\n        previous_temp = _write_owned_pointer_temp(\n            publication.root,\n            publication.pointer.name,\n            publication.pointer_before,\n        )\n        try:\n            current_identity = _capture_file_identity(publication.pointer)\n            _replace_pointer_if_version_matches(\n                previous_temp,\n                publication.pointer,\n                expected_bytes=publication.pointer_after,\n                expected_identity=current_identity,\n            )\n        except BaseException as exc:\n            cleanup_errors.append(exc)\n        finally:\n            previous_temp.unlink(missing_ok=True)\n        # Preserve immutable directories when replacing an existing pointer. Another reader or\n        # publisher may already have retained a reference to the content-addressed snapshot.\n        return\n    # If another publisher has changed/replaced the pointer, ownership is no longer exclusive;\n    # preserve both the pointer and immutable directory rather than deleting foreign state.\n    if not _pointer_version_is_current(publication):\n        return\n    try:\n        publication.pointer.unlink(missing_ok=True)\n    except BaseException as exc:\n        cleanup_errors.append(exc)\n        return\n'''
new_rollback_pointer = '''    expected_identity = (\n        publication.pointer_inode,\n        publication.pointer_mtime_ns,\n        publication.pointer_size,\n    )\n    if publication.pointer_before is not None:\n        if publication.pointer_inode < 0:\n            return\n        previous_temp = _write_owned_pointer_temp(\n            publication.root,\n            publication.pointer.name,\n            publication.pointer_before,\n        )\n        try:\n            _replace_pointer_if_version_matches(\n                previous_temp,\n                publication.pointer,\n                expected_bytes=publication.pointer_after,\n                expected_identity=expected_identity,\n            )\n        except BaseException as exc:\n            cleanup_errors.append(exc)\n        finally:\n            previous_temp.unlink(missing_ok=True)\n        # Preserve immutable directories when replacing an existing pointer. Another reader or\n        # publisher may already have retained a reference to the content-addressed snapshot.\n        return\n    if publication.pointer_inode < 0:\n        return\n    try:\n        if not _unlink_pointer_if_version_matches(\n            publication.pointer,\n            expected_bytes=publication.pointer_after,\n            expected_identity=expected_identity,\n        ):\n            return\n    except BaseException as exc:\n        cleanup_errors.append(exc)\n        return\n'''
replace_once(assembler, old_rollback_pointer, new_rollback_pointer)

old_owned_unlink = '''def _unlink_owned_file_if_current(publication: _OwnedFilePublication) -> bool:\n    if not _owned_file_is_current(publication):\n        return False\n    publication.path.unlink(missing_ok=True)\n    return True\n'''
new_owned_unlink = '''def _unlink_owned_file_if_current(publication: _OwnedFilePublication) -> bool:\n    """Remove only the exact owned inode/version after atomically claiming its name."""\n\n    path = publication.path\n    if path.is_symlink() or not path.exists():\n        return False\n    quarantine = _new_publication_quarantine(path)\n    try:\n        try:\n            os.replace(path, quarantine)\n        except FileNotFoundError:\n            return False\n        if quarantine.is_symlink() or not quarantine.is_file():\n            return False\n        try:\n            inode, mtime_ns, size = _capture_file_identity(quarantine)\n            digest = hashlib.sha256(quarantine.read_bytes()).hexdigest()\n        except OSError:\n            _restore_quarantined_file_if_absent(quarantine, path)\n            return False\n        matches = bool(\n            inode == publication.inode\n            and mtime_ns == publication.mtime_ns\n            and size == publication.size\n            and digest == publication.sha256\n        )\n        if not matches:\n            _restore_quarantined_file_if_absent(quarantine, path)\n            return False\n        # The owned version is isolated. A foreign replacement created after the\n        # atomic claim remains at the canonical pathname and is never unlinked.\n        return True\n    finally:\n        quarantine.unlink(missing_ok=True)\n'''
replace_once(assembler, old_owned_unlink, new_owned_unlink)

# ---------------------------------------------------------------------------
# Convert the primary assembler fixture from forged derived IDs to real source
# artifacts, so full-package tests exercise the same source-chain replay now
# required in production.
# ---------------------------------------------------------------------------
test = root / "tests/unit/test_research_package_assembler_v2_1.py"
replace_once(test, "from pathlib import Path\n\nimport pytest\n", "from pathlib import Path\n\nimport pandas as pd\nimport pytest\n")
replace_once(
    test,
    '''from alpha_cycle.intelligence.epistemic_defense import (\n    EpistemicDefensePackageSnapshot,\n    persist_epistemic_defense_package,\n)\n''',
    '''from alpha_cycle.intelligence.epistemic_defense import (\n    CounterExplanation,\n    CounterThesisStatus,\n    MaterialityLevel,\n    build_blind_spot_snapshot,\n    build_counter_thesis_snapshot,\n    build_epistemic_defense_package,\n    persist_blind_spot_discovery,\n    persist_counter_thesis,\n    persist_epistemic_defense_package,\n)\n''',
)
replace_once(
    test,
    '''from alpha_cycle.intelligence.forward_valuation import (\n    ForwardValuationMetric,\n    ForwardValuationObservation,\n    ForwardValuationStateSnapshot,\n    ForwardValuationStatus,\n    persist_forward_valuation_state,\n)\n''',
    '''from alpha_cycle.intelligence.forward_valuation import (\n    ForwardValuationMetric,\n    ForwardValuationStateSnapshot,\n    build_forward_valuation_state,\n    persist_forward_valuation_state,\n)\n''',
)
replace_once(
    test,
    '''from alpha_cycle.intelligence.price_implied_requirement import (\n    PriceImpliedRequirementObservation,\n    PriceImpliedRequirementSnapshot,\n    PriceImpliedRequirementStatus,\n    ReferenceFrameKind,\n    persist_price_implied_requirement,\n)\n''',
    '''from alpha_cycle.intelligence.price_implied_requirement import (\n    PriceImpliedRequirementSnapshot,\n    ReferenceFrameKind,\n    ValuationReferencePoint,\n    build_price_implied_requirement,\n    build_valuation_reference_frame,\n    persist_price_implied_requirement,\n    persist_valuation_reference_frame,\n)\n''',
)
replace_once(
    test,
    '''from alpha_cycle.intelligence.underwriter_v2_1 import (\n''',
    '''from alpha_cycle.intelligence.valuation import (\n    ValuationEvidenceSnapshot,\n    write_valuation_evidence_snapshot,\n)\nfrom alpha_cycle.intelligence.underwriter_v2_1 import (\n''',
)

start = test.read_text(encoding="utf-8")
old_helpers_start = start.index("def _forward_valuation(\n")
old_helpers_end = start.index("\ndef _components(", old_helpers_start)
new_helpers = '''def _valuation_evidence(\n    thesis: InvestmentThesisSnapshot,\n    expectations: ExpectationStateSnapshot,\n    offset: int,\n) -> ValuationEvidenceSnapshot:\n    market_cap = float(expectations.observations[0].value) * 1_000_000.0 * 10.0\n    return ValuationEvidenceSnapshot(\n        captured_at=NOW + timedelta(seconds=19 + offset),\n        evaluation_date=EVAL,\n        research_snapshot_id=A,\n        market_snapshot_id=C,\n        history_years=1,\n        shares=pd.DataFrame([{\"ticker\": thesis.security_id, \"listed_stock_cnt\": 1.0}]),\n        security_values=pd.DataFrame([{\"ticker\": thesis.security_id, \"market_value\": market_cap}]),\n        financial_history=pd.DataFrame([{\"ticker\": thesis.security_id, \"revenue\": 1.0}]),\n        valuation_metrics=pd.DataFrame(\n            [\n                {\n                    \"ticker\": thesis.security_id,\n                    \"market_cap_complete\": True,\n                    \"market_cap\": market_cap,\n                    \"valuation_score\": 3.0,\n                }\n            ]\n        ),\n        raw_valuation={\"fixture_security_id\": thesis.security_id},\n        warnings=(),\n    )\n\n\ndef _forward_valuation(\n    valuation: ValuationEvidenceSnapshot,\n    expectations: ExpectationStateSnapshot,\n    offset: int,\n) -> ForwardValuationStateSnapshot:\n    return build_forward_valuation_state(\n        valuation,\n        expectations,\n        captured_at=NOW + timedelta(seconds=23 + offset),\n    )\n\n\ndef _reference_frame(\n    thesis: InvestmentThesisSnapshot,\n    expectations: ExpectationStateSnapshot,\n    offset: int,\n):\n    expectation = expectations.observations[0]\n    return build_valuation_reference_frame(\n        captured_at=NOW + timedelta(seconds=23 + offset),\n        evaluation_date=EVAL,\n        security_id=thesis.security_id,\n        reference_points=(\n            ValuationReferencePoint(\n                reference_id=\"fixture-price-reference\",\n                metric=ForwardValuationMetric.FORWARD_PE,\n                target_period=expectation.target_period,\n                target_period_end=expectation.target_period_end,\n                reference_multiple=10.0,\n                reference_kind=ReferenceFrameKind.EXPLICIT_SCENARIO_ASSUMPTION,\n                observed_at=NOW - timedelta(hours=1),\n                rationale=\"Deterministic package-assembler fixture reference.\",\n            ),\n        ),\n    )\n\n\ndef _price_implied(\n    valuation: ValuationEvidenceSnapshot,\n    reference_frame,\n    offset: int,\n) -> PriceImpliedRequirementSnapshot:\n    return build_price_implied_requirement(\n        valuation,\n        reference_frame,\n        captured_at=NOW + timedelta(seconds=24 + offset),\n    )\n\n\ndef _epistemic_sources(thesis: InvestmentThesisSnapshot, offset: int):\n    counter = build_counter_thesis_snapshot(\n        counter_thesis_id=f\"fixture-counter-{thesis.security_id}\",\n        snapshot_version=1,\n        parent_snapshot_id=None,\n        thesis_snapshot_id=thesis.snapshot_id,\n        captured_at=NOW + timedelta(seconds=23 + offset),\n        created_without_thesis_support_search=True,\n        independence_method=\"deterministic independent fixture challenge\",\n        search_scope=(\"fixture-counter-scope\",),\n        strongest_alternative_explanation_id=\"alternative-demand\",\n        alternative_explanations=(\n            CounterExplanation(\n                explanation_id=\"alternative-demand\",\n                statement=\"Observed strength could reflect a temporary demand pull-forward.\",\n                mechanism=\"Timing rather than structural demand explains the observation.\",\n                epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,\n                materiality=MaterialityLevel.LOW,\n                supporting_evidence_refs=(),\n                opposing_evidence_refs=(),\n                falsifier=\"Demand remains durable after the fixture horizon.\",\n            ),\n        ),\n        falsification_evidence_refs=(),\n        missing_evidence=(),\n        unresolved_contradictions=(),\n        status=CounterThesisStatus.ACTIVE,\n    )\n    blind = build_blind_spot_snapshot(\n        discovery_id=f\"fixture-blind-{thesis.security_id}\",\n        snapshot_version=1,\n        parent_snapshot_id=None,\n        thesis_snapshot_id=thesis.snapshot_id,\n        captured_at=NOW + timedelta(seconds=24 + offset),\n        existing_critical_state_variables=(\"demand\",),\n        graph_variables_used_as_exclusion_set=True,\n        search_scope=(\"fixture-outside-graph-scope\",),\n        discovery_method=\"deterministic fixture outside-graph scan\",\n        search_completed=True,\n        candidates=(),\n        search_limitations=(\"fixture scope is intentionally narrow\",),\n        no_candidate_found_reason=\"No additional deterministic fixture candidate.\",\n    )\n    epistemic = build_epistemic_defense_package(\n        thesis,\n        counter,\n        blind,\n        captured_at=NOW + timedelta(seconds=25 + offset),\n    )\n    return counter, blind, epistemic\n\n'''
start = start[:old_helpers_start] + new_helpers + start[old_helpers_end + 1 :]
test.write_text(start, encoding="utf-8")

# Replace the source construction inside _components.
replace_once(
    test,
    '''    expectations = _expectations(thesis, offset)\n    forward_valuation = _forward_valuation(thesis, expectations, offset)\n    price_implied = _price_implied(thesis, expectations, offset)\n    epistemic = EpistemicDefensePackageSnapshot(\n        captured_at=NOW + timedelta(seconds=25 + offset),\n        thesis_snapshot_id=thesis.snapshot_id,\n        counter_thesis_snapshot_id=A,\n        blind_spot_snapshot_id=B,\n        guardrail_evidence_id=GUARDRAIL,\n        required_contracts_present=True,\n        high_materiality_counter_explanation_count=0,\n        high_materiality_unresolved_contradiction_count=0,\n        uncovered_high_materiality_blind_spot_count=0,\n        blind_spot_promotion_candidate_count=0,\n        research_flags=(),\n    )\n''',
    '''    expectations = _expectations(thesis, offset)\n    valuation = _valuation_evidence(thesis, expectations, offset)\n    reference_frame = _reference_frame(thesis, expectations, offset)\n    forward_valuation = _forward_valuation(valuation, expectations, offset)\n    price_implied = _price_implied(valuation, reference_frame, offset)\n    counter_thesis, blind_spot, epistemic = _epistemic_sources(thesis, offset)\n''',
)
replace_once(
    test,
    '''        price_implied,\n        epistemic,\n    )\n''',
    '''        price_implied,\n        epistemic,\n        valuation,\n        reference_frame,\n        counter_thesis,\n        blind_spot,\n    )\n''',
)
replace_once(
    test,
    '''            price_implied,\n            epistemic,\n        ) = _components(thesis, index)\n''',
    '''            price_implied,\n            epistemic,\n            valuation,\n            reference_frame,\n            counter_thesis,\n            blind_spot,\n        ) = _components(thesis, index)\n''',
)
replace_once(
    test,
    '''        persist_expectation_state(\n            expectations,\n            output_root=tmp_path / "expectation_state",\n        )\n        persist_forward_valuation_state(\n''',
    '''        persist_expectation_state(\n            expectations,\n            output_root=tmp_path / "expectation_state",\n        )\n        write_valuation_evidence_snapshot(tmp_path / "valuation_evidence", valuation)\n        persist_valuation_reference_frame(reference_frame, output_root=tmp_path)\n        persist_counter_thesis(counter_thesis, output_root=tmp_path)\n        persist_blind_spot_discovery(blind_spot, output_root=tmp_path)\n        persist_forward_valuation_state(\n''',
)

# ---------------------------------------------------------------------------
# Adversarial regressions for the three source-chain findings and both TOCTOU
# findings.  These target the exact mechanism, not just happy-path assembly.
# ---------------------------------------------------------------------------
new_test = root / "tests/unit/test_research_package_exact_head_review_v2_1.py"
new_test.write_text(
    '''from __future__ import annotations\n\nimport hashlib\nimport os\nfrom dataclasses import replace\nfrom pathlib import Path\n\nimport pytest\n\nimport alpha_cycle.research_package_assembler_v2_1 as assembler\nfrom alpha_cycle.research_package_source_revalidation_v2_1 import (\n    epistemic_package_sources_are_canonical,\n    forward_valuation_sources_are_canonical,\n    price_implied_sources_are_canonical,\n)\nfrom tests.unit.test_research_package_assembler_v2_1 import (\n    _components,\n    _persist_components,\n    _prepare_ready_request,\n)\n\n\ndef _materialized_sources(tmp_path: Path):\n    theses = _prepare_ready_request(tmp_path)\n    _persist_components(tmp_path, theses)\n    components = _components(theses[0], 0)\n    return theses[0], components\n\n\ndef test_epistemic_package_requires_real_counter_and_blind_spot_sources(tmp_path: Path) -> None:\n    thesis, components = _materialized_sources(tmp_path)\n    epistemic = components[11]\n    forged = replace(epistemic, counter_thesis_snapshot_id=\"f\" * 64)\n\n    assert epistemic_package_sources_are_canonical(\n        tmp_path, thesis=thesis, snapshot=epistemic\n    ) is True\n    assert epistemic_package_sources_are_canonical(\n        tmp_path, thesis=thesis, snapshot=forged\n    ) is False\n\n\ndef test_forward_valuation_requires_real_market_cap_source(tmp_path: Path) -> None:\n    _thesis, components = _materialized_sources(tmp_path)\n    expectations = components[8]\n    forward = components[9]\n    forged = replace(forward, valuation_evidence_snapshot_id=\"f\" * 64)\n\n    assert forward_valuation_sources_are_canonical(\n        tmp_path, snapshot=forward, expectations=expectations\n    ) is True\n    assert forward_valuation_sources_are_canonical(\n        tmp_path, snapshot=forged, expectations=expectations\n    ) is False\n\n\ndef test_price_implied_requires_real_valuation_and_reference_frame(tmp_path: Path) -> None:\n    _thesis, components = _materialized_sources(tmp_path)\n    price_implied = components[10]\n    forged = replace(price_implied, reference_frame_snapshot_id=\"f\" * 64)\n\n    assert price_implied_sources_are_canonical(tmp_path, snapshot=price_implied) is True\n    assert price_implied_sources_are_canonical(tmp_path, snapshot=forged) is False\n\n\ndef test_conditional_pointer_publish_never_overwrites_concurrent_replacement(\n    tmp_path: Path, monkeypatch: pytest.MonkeyPatch\n) -> None:\n    pointer = tmp_path / \"latest.json\"\n    pointer.write_bytes(b\"old\")\n    expected_identity = assembler._capture_file_identity(pointer)\n    replacement = assembler._write_owned_pointer_temp(tmp_path, pointer.name, b\"ours\")\n    foreign = b\"foreign\"\n    real_link = os.link\n\n    def racing_link(src, dst, *args, **kwargs):\n        if Path(dst) == pointer and Path(src) == replacement and not pointer.exists():\n            pointer.write_bytes(foreign)\n        return real_link(src, dst, *args, **kwargs)\n\n    monkeypatch.setattr(os, \"link\", racing_link)\n    try:\n        assert (\n            assembler._replace_pointer_if_version_matches(\n                replacement,\n                pointer,\n                expected_bytes=b\"old\",\n                expected_identity=expected_identity,\n            )\n            is False\n        )\n        assert pointer.read_bytes() == foreign\n    finally:\n        replacement.unlink(missing_ok=True)\n\n\ndef test_owned_file_rollback_never_deletes_concurrent_replacement(\n    tmp_path: Path, monkeypatch: pytest.MonkeyPatch\n) -> None:\n    path = tmp_path / \"round.json\"\n    path.write_bytes(b\"owned\")\n    publication = assembler._capture_owned_file(path)\n    real_replace = os.replace\n    foreign = b\"foreign-round\"\n    injected = False\n\n    def racing_replace(src, dst, *args, **kwargs):\n        nonlocal injected\n        result = real_replace(src, dst, *args, **kwargs)\n        if Path(src) == path and not injected:\n            injected = True\n            path.write_bytes(foreign)\n        return result\n\n    monkeypatch.setattr(os, \"replace\", racing_replace)\n    assert assembler._unlink_owned_file_if_current(publication) is True\n    assert path.read_bytes() == foreign\n    assert hashlib.sha256(path.read_bytes()).hexdigest() != publication.sha256\n''',
    encoding="utf-8",
)

# ---------------------------------------------------------------------------
# Keep operator documentation aligned with the stronger final gate.
# ---------------------------------------------------------------------------
doc = root / "docs/TYPED_RESEARCH_PACKAGE_ASSEMBLER_V2_1.md"
replace_once(
    doc,
    '''Persisted builder outputs are additionally checked for canonical invariants that their dataclasses alone do not enforce:\n''',
    '''Persisted builder outputs are additionally checked for canonical invariants that their dataclasses alone do not enforce. Derived evidence is accepted only when its persisted source contracts can also be reconstructed and the owning canonical builder reproduces the exact derived snapshot:\n''',
)
replace_once(
    doc,
    '''Opportunity rollback is ownership-aware and monotonic: it removes only immutable snapshot directories that this publication call actually created, and it never restores an older pointer over a concurrently changed pointer version. If ownership is ambiguous after a concurrent publisher wins a race, valid immutable state is preserved instead of deleted. Publication remains ledger-last.\n''',
    '''Opportunity rollback is ownership-aware and monotonic. Mutable pointer replacement and rollback deletion atomically claim the current pathname into an unpredictable same-directory quarantine before validating its version; publication/restoration uses no-replace links, so a direct concurrent publisher that recreates the canonical name always wins. Round/run rollback uses the same claim-before-delete rule and therefore cannot unlink a foreign replacement after a separate ownership check. Immutable snapshot directories are removed only when this publication call created them and ownership remains exclusive. Publication remains ledger-last.\n''',
)

print("PR303 final review hardening patch applied")
