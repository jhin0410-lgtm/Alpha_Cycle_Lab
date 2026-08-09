"""Small regression checks for the optional KOSIS source entrypoints."""

from pathlib import Path


def test_kosis_discovery_entrypoints_and_optional_environment_contract() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    env_example = Path(".env.example").read_text(encoding="utf-8")
    runner = Path("scripts/run_live_pipeline.ps1").read_text(encoding="utf-8")

    assert (
        'alpha-cycle-kosis-discovery = "alpha_cycle.kosis_industry_discovery_cli:main"'
        in pyproject
    )
    assert (
        "alpha-cycle-kosis-semiconductor-sources = "
        '"alpha_cycle.kosis_semiconductor_source_discovery_cli:main"'
        in pyproject
    )
    assert (
        "alpha-cycle-kosis-semiconductor-history = "
        '"alpha_cycle.kosis_semiconductor_history_cli:main"'
        in pyproject
    )
    assert "KOSIS_API_KEY=replace_with_local_secret" in env_example
    assert '"KOSIS_API_KEY"' not in runner
