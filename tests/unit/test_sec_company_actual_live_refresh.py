from pathlib import Path

BOOTSTRAP = Path("scripts/run_live_pipeline_bootstrap.ps1")
REFRESH = Path("scripts/refresh_sec_company_actual.ps1")


def test_live_bootstrap_refreshes_sec_actual_after_opendart_and_before_pipeline() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    opendart_call = "& $ProvisionalEarningsRefresh @PipelineArguments"
    sec_call = "& $SecCompanyActualRefresh @PipelineArguments"
    pipeline_call = "& $Pipeline @PipelineArguments"

    assert '"refresh_sec_company_actual.ps1"' in text
    assert opendart_call in text
    assert sec_call in text
    assert pipeline_call in text
    assert text.index(opendart_call) < text.index(sec_call) < text.index(pipeline_call)


def test_sec_refresh_requires_declared_user_agent_but_remains_best_effort() -> None:
    text = REFRESH.read_text(encoding="utf-8")

    assert "$EvaluationDate = Resolve-EvaluationDate -Arguments $PipelineArguments" in text
    assert "Korea Standard Time" in text
    assert "SEC_EDGAR_USER_AGENT" in text
    assert "alpha_cycle.sec_company_actual_cli" in text
    assert "skhynix_000660_2026q2_sec_6k_actual" in text
    assert "--evaluation-date $EvaluationDate" in text
    assert 'Join-Path $OutputRoot "sec-company-actual"' in text
    assert "cross-check will remain unavailable" in text
    assert text.rstrip().endswith("exit 0")
