"""Regression checks for provenance binding and publication rollback."""

from __future__ import annotations

from pathlib import Path


def test_pipeline_binds_canonical_artifacts_without_copying_them() -> None:
    source = Path("src/alpha_cycle/pipeline_market_consistency.py").read_text(
        encoding="utf-8"
    )

    assert "def _load_exact_provenance(" in source
    assert 'raw_pointer.get("result_id") != raw_result.result_id' in source
    assert 'scope_pointer.get("assessment_id") != assessment.assessment_id' in source
    assert "load_market_consistency_provenance(" in source
    assert "raw_pointer_after != raw_pointer_before" in source
    assert "scope_pointer_after != scope_pointer_before" in source
    assert "def _validate_loaded_provenance(" in source
    assert 'TemporaryDirectory(prefix="pipeline-provenance-")' not in source
    assert "shutil.copy2(raw_result_path, isolated_result)" not in source


def test_decision_failure_removes_only_new_envelope() -> None:
    source = Path("src/alpha_cycle/intelligence/decision_publication.py").read_text(
        encoding="utf-8"
    )

    assert "def _publish_directory(" in source
    assert ") -> bool:" in source
    assert "return False" in source
    assert "return True" in source
    assert "envelope_created_by_run = _publish_directory(" in source
    assert "shutil.rmtree(published_envelope_directory)" in source
