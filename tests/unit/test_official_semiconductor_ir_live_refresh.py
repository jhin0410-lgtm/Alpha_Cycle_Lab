from pathlib import Path

BOOTSTRAP = Path("scripts/run_live_pipeline_bootstrap.ps1")
REFRESH = Path("scripts/refresh_official_semiconductor_ir.ps1")


def test_live_bootstrap_runs_official_ir_refresh_before_pipeline() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    refresh_call = "& $OfficialIrRefresh @PipelineArguments"
    pipeline_call = "& $Pipeline @PipelineArguments"
    assert '"refresh_official_semiconductor_ir.ps1"' in text
    assert refresh_call in text
    assert pipeline_call in text
    assert text.index(refresh_call) < text.index(pipeline_call)


def test_official_ir_refresh_is_best_effort_and_uses_pipeline_evaluation_date() -> None:
    text = REFRESH.read_text(encoding="utf-8")
    assert 'Get-OptionValue -Arguments $Arguments -Name "--evaluation-date"' in text
    assert "$EvaluationDate = Resolve-EvaluationDate -Arguments $PipelineArguments" in text
    assert "Korea Standard Time" in text
    assert "alpha_cycle.official_semiconductor_ir_refresh_cli" in text
    assert "--evaluation-date $EvaluationDate" in text
    assert "--document-output $DocumentOutput" in text
    assert "--baseline-output $BaselineOutput" in text
    assert "--forward-output $ForwardOutput" in text
    warning = "live pipeline will continue without treating stale official IR evidence as current"
    assert warning in text
    assert text.rstrip().endswith("exit 0")


def test_official_ir_refresh_keeps_downstream_outputs_under_live_research_root() -> None:
    text = REFRESH.read_text(encoding="utf-8")
    assert 'Join-Path $OutputRoot "official-semiconductor-ir-refresh"' in text
    assert 'Join-Path $OutputRoot "official-semiconductor-ir-documents"' in text
    assert 'Join-Path $OutputRoot "semiconductor-baseline-reconciliation"' in text
    assert 'Join-Path $OutputRoot "semiconductor-forward-input-evidence"' in text
