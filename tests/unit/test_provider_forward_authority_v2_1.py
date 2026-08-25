"""Adversarial regressions for provider-specific forward source authority v2.1."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import alpha_cycle.provider_forward_authority_v2_1 as authority_module
from alpha_cycle.intelligence.expectation_gap_contract import ExpectationSemantics
from alpha_cycle.intelligence.expectation_state import (
    CertifiedExpectationObservation,
    ExpectationKind,
    ExpectationMetric,
    ExpectationStateSnapshot,
)
from alpha_cycle.intelligence.expectations import (
    ExpectationIntelligenceSnapshot,
    write_expectation_intelligence_snapshot,
)
from alpha_cycle.provider_forward_authority_v2_1 import (
    ProviderForwardAuthorityError,
    build_kis_provider_authority,
    provider_authority_can_certify_expectation,
    publish_kis_provider_authority,
    replay_kis_provider_authority,
)
from alpha_cycle.providers.kis_research import (
    KIS_ESTIMATE_PERFORM_ENDPOINT,
    KIS_ESTIMATE_PERFORM_TR_ID,
    KIS_RESEARCH_SOURCE_SCOPE,
    KisEstimatePerformEvidence,
)
from alpha_cycle.research_package_source_revalidation_v2_1 import (
    expectation_sources_are_canonical,
)

KST = ZoneInfo("Asia/Seoul")
CAPTURED = datetime(2026, 8, 10, 13, 33, tzinfo=KST)
EVALUATION_DATE = date(2026, 8, 10)


def _payload(
    symbol: str,
    *,
    reported_symbol: str | None = None,
    rt_cd: str = "0",
    null_field: bool = False,
) -> dict[str, object]:
    seed = 100 if symbol == "000660" else 200
    row = {f"data{index}": str(seed + index) for index in range(1, 6)}
    output2 = [dict(row) for _ in range(6)]
    if null_field:
        output2[0]["data4"] = None
    return {
        "rt_cd": rt_cd,
        "msg_cd": "MCA00000",
        "msg1": "ok",
        "output1": {
            "sht_cd": f"A{reported_symbol or symbol}",
            "estdate": "20260630",
        },
        "output2": output2,
        "output3": [dict(row) for _ in range(3)],
        "output4": [
            {"dt": "2023.12"},
            {"dt": "2024.12"},
            {"dt": "2025.12"},
            {"dt": "2026.12E"},
            {"dt": "2027.12E"},
        ],
    }


def _source(
    tmp_path: Path,
    *,
    future_record: bool = False,
    reported_symbol: str | None = None,
    rt_cd: str = "0",
    null_field: bool = False,
) -> Path:
    records = tuple(
        KisEstimatePerformEvidence(
            symbol=symbol,
            retrieved_at=(
                CAPTURED + timedelta(minutes=1)
                if future_record and symbol == "005930"
                else CAPTURED - timedelta(seconds=offset)
            ),
            endpoint=KIS_ESTIMATE_PERFORM_ENDPOINT,
            tr_id=KIS_ESTIMATE_PERFORM_TR_ID,
            source_scope=KIS_RESEARCH_SOURCE_SCOPE,
            raw_response_sha256=("a" if symbol == "000660" else "b") * 64,
            raw_payload=_payload(
                symbol,
                reported_symbol=(
                    reported_symbol if symbol == "000660" else None
                ),
                rt_cd=rt_cd,
                null_field=null_field and symbol == "000660",
            ),
        )
        for offset, symbol in enumerate(("000660", "005930"), start=1)
    )
    snapshot = ExpectationIntelligenceSnapshot(
        captured_at=(
            CAPTURED - timedelta(seconds=1)
            if future_record
            else max(item.retrieved_at for item in records)
        ),
        provider="korea_investment_openapi",
        source_scope=KIS_RESEARCH_SOURCE_SCOPE,
        records=records,
    )
    paths = write_expectation_intelligence_snapshot(tmp_path / "source", snapshot)
    return paths[0].parent


def _published(tmp_path: Path) -> tuple[Path, object]:
    source = _source(tmp_path)
    directory = publish_kis_provider_authority(
        source,
        evaluation_date=EVALUATION_DATE,
        research_cutoff_at=CAPTURED,
        output_root=tmp_path / "provider_forward_authority_v2_1",
    )
    return directory, replay_kis_provider_authority(
        directory,
        evaluation_date=EVALUATION_DATE,
        research_cutoff_at=CAPTURED,
    )


def _rewrite_json(path: Path, mutate) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_real_parser_replays_source_bytes_without_semantic_promotion(tmp_path: Path) -> None:
    directory, artifact = _published(tmp_path)
    assert directory.is_dir()
    assert artifact.symbols == ("000660", "005930")
    assert artifact.payload_without_id()["provider_capture_replay_integrity"] is True
    assert artifact.payload_without_id()["provider_source_authority"] is False
    assert artifact.payload_without_id()["provider_forward_numeric_authority"] is False
    assert artifact.payload_without_id()["market_consensus_authority"] is False
    assert artifact.payload_without_id()["original_http_response_bytes_archived"] is False
    assert len(artifact.cells) == 90


@pytest.mark.parametrize(
    ("provider", "security", "metric", "period", "consensus"),
    [
        ("korea_investment_openapi", "000660", "revenue", "2026.12E", True),
        ("korea_investment_openapi", "000660", "eps", "2026.12E", False),
        ("korea_investment_openapi", "005930", "operating_income", "2025.12E", False),
        ("korea_investment_openapi", "999999", "revenue", "2026.12E", False),
        ("spoofed_kis", "000660", "revenue", "2026.12E", False),
        ("unknown_provider", "000660", "revenue", "2026.12E", True),
    ],
)
def test_labels_wrong_security_metric_period_or_provider_never_create_authority(
    tmp_path: Path,
    provider: str,
    security: str,
    metric: str,
    period: str,
    consensus: bool,
) -> None:
    _, artifact = _published(tmp_path)
    assert not provider_authority_can_certify_expectation(
        artifact,
        provider_id=provider,
        security_id=security,
        metric=metric,
        target_period=period,
        market_consensus_certified=consensus,
    )


def test_normalized_forward_without_raw_source_is_rejected(tmp_path: Path) -> None:
    directory, _ = _published(tmp_path)
    (directory / "raw_estimate_perform.json").unlink()
    with pytest.raises(ProviderForwardAuthorityError, match="missing"):
        replay_kis_provider_authority(
            directory, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )


def test_provider_name_spoofing_is_rejected_at_source(tmp_path: Path) -> None:
    source = _source(tmp_path)
    _rewrite_json(source / "records.json", lambda value: value[0].__setitem__("provider", "kis"))
    with pytest.raises(ProviderForwardAuthorityError, match="spoofing"):
        build_kis_provider_authority(
            source, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )


def test_source_manifest_provider_mismatch_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    _rewrite_json(source / "manifest.json", lambda value: value.__setitem__("provider", "fake"))
    with pytest.raises(ProviderForwardAuthorityError, match="provider/schema"):
        build_kis_provider_authority(
            source, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )


def test_future_source_and_future_revision_cutoffs_are_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    with pytest.raises(ProviderForwardAuthorityError, match="after"):
        build_kis_provider_authority(
            source,
            evaluation_date=EVALUATION_DATE,
            research_cutoff_at=CAPTURED - timedelta(minutes=1),
        )
    with pytest.raises(ProviderForwardAuthorityError, match="after"):
        build_kis_provider_authority(
            source,
            evaluation_date=date(2026, 8, 9),
            research_cutoff_at=CAPTURED - timedelta(days=1),
        )
    directory, _ = _published(tmp_path / "second")
    with pytest.raises(ProviderForwardAuthorityError, match="after"):
        replay_kis_provider_authority(
            directory,
            evaluation_date=date(2026, 8, 9),
            research_cutoff_at=CAPTURED - timedelta(days=1),
        )


def test_canonical_utc_cutoff_uses_korean_evaluation_date(tmp_path: Path) -> None:
    source = _source(tmp_path)
    artifact = build_kis_provider_authority(
        source,
        evaluation_date=EVALUATION_DATE,
        research_cutoff_at=CAPTURED.astimezone(ZoneInfo("UTC")),
    )
    assert artifact.evaluation_date == EVALUATION_DATE


def test_record_after_cutoff_and_stale_manifest_capture_are_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, future_record=True)
    with pytest.raises(ProviderForwardAuthorityError, match="retrieved after|latest record"):
        build_kis_provider_authority(
            source,
            evaluation_date=EVALUATION_DATE,
            research_cutoff_at=CAPTURED,
        )


def test_provider_reported_security_must_match_requested_record(tmp_path: Path) -> None:
    source = _source(tmp_path, reported_symbol="005930")
    with pytest.raises(ProviderForwardAuthorityError, match="reported security"):
        build_kis_provider_authority(
            source,
            evaluation_date=EVALUATION_DATE,
            research_cutoff_at=CAPTURED,
        )


def test_unsuccessful_kis_envelope_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, rt_cd="1")
    with pytest.raises(ProviderForwardAuthorityError, match="not successful"):
        build_kis_provider_authority(
            source,
            evaluation_date=EVALUATION_DATE,
            research_cutoff_at=CAPTURED,
        )


def test_stale_revision_substitution_is_rejected(tmp_path: Path) -> None:
    directory, _ = _published(tmp_path)
    with pytest.raises(ProviderForwardAuthorityError, match="stale or substituted"):
        replay_kis_provider_authority(
            directory,
            evaluation_date=EVALUATION_DATE,
            research_cutoff_at=CAPTURED,
            expected_artifact_id="0" * 64,
        )


def test_raw_source_mutation_is_rejected(tmp_path: Path) -> None:
    directory, _ = _published(tmp_path)
    path = directory / "raw_estimate_perform.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ProviderForwardAuthorityError, match="mutation"):
        replay_kis_provider_authority(
            directory, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )


def test_normalized_artifact_mutation_is_rejected_even_with_updated_file_hash(
    tmp_path: Path,
) -> None:
    directory, _ = _published(tmp_path)
    authority_path = directory / "authority.json"
    _rewrite_json(
        authority_path,
        lambda value: value.__setitem__("market_consensus_authority", True),
    )
    manifest_path = directory / "manifest.json"
    _rewrite_json(
        manifest_path,
        lambda value: value["file_sha256"].__setitem__(
            "authority.json", authority_module._digest(authority_path.read_bytes())
        ),
    )
    with pytest.raises(ProviderForwardAuthorityError, match="normalized artifact mutation"):
        replay_kis_provider_authority(
            directory, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )


def test_outer_manifest_capture_timestamp_and_directory_identity_are_bound(
    tmp_path: Path,
) -> None:
    directory, _ = _published(tmp_path)
    manifest_path = directory / "manifest.json"
    _rewrite_json(
        manifest_path,
        lambda value: value.__setitem__(
            "captured_at", (CAPTURED - timedelta(days=1)).isoformat()
        ),
    )
    with pytest.raises(ProviderForwardAuthorityError, match="capture timestamp"):
        replay_kis_provider_authority(
            directory, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )

    # Restore a valid publication before testing canonical directory naming.
    _rewrite_json(
        manifest_path,
        lambda value: value.__setitem__(
            "captured_at", (CAPTURED - timedelta(seconds=1)).isoformat()
        ),
    )
    moved = directory.parent / f"wrong__{directory.name.split('__', 1)[1]}"
    directory.rename(moved)
    with pytest.raises(ProviderForwardAuthorityError, match="directory identity"):
        replay_kis_provider_authority(
            moved, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )


def test_parser_change_cannot_silently_change_normalized_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, artifact = _published(tmp_path)
    monkeypatch.setattr(authority_module, "_opaque_cells", lambda raw, symbols: artifact.cells[:-1])
    with pytest.raises(ProviderForwardAuthorityError, match="parser replay mismatch"):
        replay_kis_provider_authority(
            directory, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )


def test_replay_makes_zero_network_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory, _ = _published(tmp_path)
    monkeypatch.setattr(
        "socket.socket.connect",
        lambda *args, **kwargs: pytest.fail("replay attempted network access"),
    )
    replay_kis_provider_authority(
        directory, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
    )


def test_latest_endpoint_never_claims_complete_revision_history(tmp_path: Path) -> None:
    _, artifact = _published(tmp_path)
    payload = artifact.payload_without_id()
    assert payload["revision_sequence"] == 0
    assert payload["revision_history_complete"] is False
    assert payload["historical_point_in_time_complete"] is False
    assert payload["revision_authority"] is False


def test_unsupported_field_is_not_converted_to_zero(tmp_path: Path) -> None:
    source = _source(tmp_path, null_field=True)
    with pytest.raises(ProviderForwardAuthorityError, match="cannot become zero"):
        build_kis_provider_authority(
            source, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )


def _self_certified_expectation(source_id: str) -> ExpectationStateSnapshot:
    semantics = ExpectationSemantics(
        provider_id="korea_investment_openapi",
        provider_semantics_certified=True,
        target_period_semantics_certified=True,
        metric_semantics_certified=True,
        aggregation_semantics_certified=True,
        observation_timestamp_certified=True,
        provider_vintage_certified=True,
        comparable_prior_snapshot_available=True,
        comparable_snapshot_scope_certified=True,
        revision_calculation_certified=True,
        numeric_evidence_available=True,
        source_scope=KIS_RESEARCH_SOURCE_SCOPE,
    )
    observation = CertifiedExpectationObservation(
        security_id="000660",
        metric=ExpectationMetric.REVENUE,
        target_period="2026.12E",
        target_period_end=date(2026, 12, 31),
        expectation_kind=ExpectationKind.MARKET_CONSENSUS,
        value=1.0,
        unit="KRW",
        observed_at=CAPTURED - timedelta(minutes=1),
        source_evidence_id=source_id,
        semantics=semantics,
        market_consensus_certified=True,
        aggregation_method="caller_declared_mean",
    )
    return ExpectationStateSnapshot(
        captured_at=CAPTURED,
        evaluation_date=EVALUATION_DATE,
        observations=(observation,),
        source_snapshot_ids=(source_id,),
    )


def test_caller_consensus_flag_and_kis_relabel_cannot_pass_package_authority(
    tmp_path: Path,
) -> None:
    _, artifact = _published(tmp_path)
    snapshot = _self_certified_expectation(artifact.artifact_id)
    assert not expectation_sources_are_canonical(tmp_path, snapshot=snapshot)


def test_duplicate_revision_identity_is_ambiguous_and_fails_closed(tmp_path: Path) -> None:
    directory, artifact = _published(tmp_path)
    duplicate = directory.parent / f"duplicate__{artifact.artifact_id[:12]}"
    shutil.copytree(directory, duplicate)
    assert not expectation_sources_are_canonical(
        tmp_path, snapshot=_self_certified_expectation(artifact.artifact_id)
    )


def test_repository_enumeration_error_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, artifact = _published(tmp_path)
    repository = directory.parent
    original = Path.iterdir

    def unreadable(path: Path):
        if path == repository:
            raise PermissionError("unreadable provider repository")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", unreadable)
    assert not expectation_sources_are_canonical(
        tmp_path, snapshot=_self_certified_expectation(artifact.artifact_id)
    )


@pytest.mark.parametrize(
    "caller_label",
    [
        "official_issuer_guidance",
        "single_broker_estimate",
        "multiple_provider_consensus",
        "derived_model_estimate",
    ],
)
def test_guidance_broker_consensus_and_model_relabels_remain_unsupported(
    tmp_path: Path, caller_label: str
) -> None:
    _, artifact = _published(tmp_path)
    assert caller_label not in {
        artifact.payload_without_id()["semantic_class"],
    }
    assert artifact.payload_without_id()["market_consensus_authority"] is False


def test_symlinked_raw_source_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    raw = source / "raw_estimate_perform.json"
    target = tmp_path / "raw-copy.json"
    target.write_bytes(raw.read_bytes())
    raw.unlink()
    try:
        raw.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ProviderForwardAuthorityError, match="missing"):
        build_kis_provider_authority(
            source, evaluation_date=EVALUATION_DATE, research_cutoff_at=CAPTURED
        )
