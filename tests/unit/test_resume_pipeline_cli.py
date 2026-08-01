"""Tests for resuming from linked same-day source snapshots."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from alpha_cycle import resume_pipeline_cli as resume


def _write_files(directory: Path, names: tuple[str, ...]) -> None:
    directory.mkdir(parents=True)
    for name in names:
        if name == "manifest.json":
            continue
        (directory / name).write_text("stub", encoding="utf-8")


def _write_pair(
    root: Path,
    *,
    market_name: str,
    research_name: str,
    captured_at: datetime,
    evaluation_date: date,
    market_id: str,
    symbols: list[str] | None = None,
) -> tuple[Path, Path]:
    market = root / "market-intelligence" / market_name
    research = root / "research-intelligence" / research_name
    _write_files(market, resume._REQUIRED_MARKET_FILES)
    _write_files(research, resume._REQUIRED_RESEARCH_FILES)
    (market / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": market_id,
                "captured_at": captured_at.isoformat(),
                "symbols": symbols or ["000660", "005930", "005935"],
                "interval": "1d",
                "adjusted": False,
            }
        ),
        encoding="utf-8",
    )
    (research / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": "b" * 64,
                "evaluation_date": evaluation_date.isoformat(),
                "market_snapshot_id": market_id,
            }
        ),
        encoding="utf-8",
    )
    return market, research


def test_find_resume_pair_accepts_linked_same_day_snapshot(tmp_path: Path) -> None:
    now = datetime(2026, 8, 1, 12, tzinfo=UTC)
    market, research = _write_pair(
        tmp_path,
        market_name="20260801T100000000000Z__aaaaaaaaaaaa",
        research_name="20260801T103000000000Z__bbbbbbbbbbbb",
        captured_at=now - timedelta(hours=2),
        evaluation_date=date(2026, 8, 1),
        market_id="a" * 64,
    )

    pair = resume.find_resume_pair(
        tmp_path,
        evaluation_date=date(2026, 8, 1),
        now=now,
        max_age_hours=24,
    )

    assert pair is not None
    assert pair.market_directory == market
    assert pair.research_directory == research
    assert pair.age == timedelta(hours=2)


def test_find_resume_pair_rejects_stale_snapshot(tmp_path: Path) -> None:
    now = datetime(2026, 8, 1, 12, tzinfo=UTC)
    _write_pair(
        tmp_path,
        market_name="20260731T100000000000Z__aaaaaaaaaaaa",
        research_name="20260801T103000000000Z__bbbbbbbbbbbb",
        captured_at=now - timedelta(hours=25),
        evaluation_date=date(2026, 8, 1),
        market_id="a" * 64,
    )

    assert (
        resume.find_resume_pair(
            tmp_path,
            evaluation_date=date(2026, 8, 1),
            now=now,
            max_age_hours=24,
        )
        is None
    )


def test_find_resume_pair_rejects_missing_preferred_share(tmp_path: Path) -> None:
    now = datetime(2026, 8, 1, 12, tzinfo=UTC)
    _write_pair(
        tmp_path,
        market_name="20260801T100000000000Z__aaaaaaaaaaaa",
        research_name="20260801T103000000000Z__bbbbbbbbbbbb",
        captured_at=now - timedelta(hours=1),
        evaluation_date=date(2026, 8, 1),
        market_id="a" * 64,
        symbols=["000660", "005930"],
    )

    assert (
        resume.find_resume_pair(
            tmp_path,
            evaluation_date=date(2026, 8, 1),
            now=now,
            max_age_hours=24,
        )
        is None
    )


def test_find_resume_pair_uses_newest_compatible_research(tmp_path: Path) -> None:
    now = datetime(2026, 8, 1, 12, tzinfo=UTC)
    _, older = _write_pair(
        tmp_path,
        market_name="20260801T090000000000Z__aaaaaaaaaaaa",
        research_name="20260801T093000000000Z__bbbbbbbbbbbb",
        captured_at=now - timedelta(hours=3),
        evaluation_date=date(2026, 8, 1),
        market_id="a" * 64,
    )
    _, newer = _write_pair(
        tmp_path,
        market_name="20260801T100000000000Z__cccccccccccc",
        research_name="20260801T103000000000Z__dddddddddddd",
        captured_at=now - timedelta(hours=2),
        evaluation_date=date(2026, 8, 1),
        market_id="c" * 64,
    )

    pair = resume.find_resume_pair(
        tmp_path,
        evaluation_date=date(2026, 8, 1),
        now=now,
        max_age_hours=24,
    )

    assert pair is not None
    assert pair.research_directory == newer
    assert pair.research_directory != older


def test_windows_runner_attempts_resume_only_after_ip_block() -> None:
    script = Path("scripts/run_live_pipeline.ps1").read_text(encoding="utf-8")
    assert '$status.reason -eq "tossinvest_ip_allowlist"' in script
    assert "python -m alpha_cycle.resume_pipeline_cli" in script
    assert "No completed report is available for this run." in script
