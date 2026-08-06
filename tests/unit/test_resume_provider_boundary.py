"""Regression tests for provider-safe resumed market selection."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from alpha_cycle import resume_pipeline_provenance_cli as provenance_resume


def _finder_with_provider(
    provider: str | None,
):
    def finder(
        root: Path,
        snapshot_id: str,
    ) -> tuple[Path, Mapping[str, object]] | None:
        manifest: dict[str, object] = {"snapshot_id": snapshot_id}
        if provider is not None:
            manifest["provider"] = provider
        return root / snapshot_id, manifest

    return finder


def test_toss_snapshot_remains_eligible_for_generic_resume(tmp_path: Path) -> None:
    result = provenance_resume._find_toss_resume_market(
        _finder_with_provider("tossinvest-readonly"),
        tmp_path,
        "a" * 64,
    )

    assert result is not None
    directory, manifest = result
    assert directory == tmp_path / ("a" * 64)
    assert manifest["provider"] == "tossinvest-readonly"


def test_kiwoom_snapshot_is_rejected_before_toss_consistency_gate(
    tmp_path: Path,
) -> None:
    result = provenance_resume._find_toss_resume_market(
        _finder_with_provider("kiwoom_openapi_plus"),
        tmp_path,
        "b" * 64,
    )

    assert result is None


def test_unknown_provider_is_fail_closed(tmp_path: Path) -> None:
    result = provenance_resume._find_toss_resume_market(
        _finder_with_provider(None),
        tmp_path,
        "c" * 64,
    )

    assert result is None


def test_missing_snapshot_stays_unavailable(tmp_path: Path) -> None:
    def missing(
        _root: Path,
        _snapshot_id: str,
    ) -> tuple[Path, Mapping[str, object]] | None:
        return None

    assert (
        provenance_resume._find_toss_resume_market(
            missing,
            tmp_path,
            "d" * 64,
        )
        is None
    )


def test_resume_main_patches_and_restores_market_finder() -> None:
    source = Path("src/alpha_cycle/resume_pipeline_provenance_cli.py").read_text(
        encoding="utf-8"
    )

    assert 'original_find_market: Any = getattr(resume, _FIND_MARKET_ATTRIBUTE)' in source
    assert 'setattr(resume, _FIND_MARKET_ATTRIBUTE, provider_bound_find_market)' in source
    assert 'setattr(resume, _FIND_MARKET_ATTRIBUTE, original_find_market)' in source
