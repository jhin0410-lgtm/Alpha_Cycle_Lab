from pathlib import Path

BOOTSTRAP = Path("scripts/run_live_pipeline_bootstrap.ps1")
REFRESH = Path("scripts/refresh_opendart_provisional_earnings.ps1")


def test_live_bootstrap_refreshes_provisional_earnings_before_pipeline() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    provisional_call = "& $ProvisionalEarningsRefresh @PipelineArguments"
    pipeline_call = "& $Pipeline @PipelineArguments"
    assert '"refresh_opendart_provisional_earnings.ps1"' in text
    assert provisional_call in text
    assert pipeline_call in text
    assert text.index(provisional_call) < text.index(pipeline_call)


def test_provisional_refresh_uses_same_live_evaluation_date_and_is_best_effort() -> None:
    text = REFRESH.read_text(encoding="utf-8")
    assert "$EvaluationDate = Resolve-EvaluationDate -Arguments $PipelineArguments" in text
    assert "Korea Standard Time" in text
    assert "alpha_cycle.opendart_provisional_earnings_cli" in text
    assert "skhynix_000660_2026q2_provisional" in text
    assert "--evaluation-date $EvaluationDate" in text
    assert 'Join-Path $OutputRoot "opendart-provisional-earnings"' in text
    assert "company-level provisional actual evidence will remain unavailable" in text
    assert text.rstrip().endswith("exit 0")
