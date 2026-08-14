from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import alpha_cycle.intelligence.sec_post_earnings_product_mix_scout as scout_module
from alpha_cycle.intelligence.sec_post_earnings_product_mix_scout import (
    capture_post_earnings_product_mix_scout,
)

OBSERVED_DATE = date(2026, 8, 15)
AFTER_DATE = date(2026, 7, 29)


def _submissions() -> bytes:
    return json.dumps(
        {
            "cik": "0002120882",
            "filings": {
                "recent": {
                    "accessionNumber": ["0001193125-26-341163"],
                    "filingDate": ["2026-08-10"],
                    "form": ["6-K"],
                    "primaryDocument": ["d64707d6k.htm"],
                }
            },
        }
    ).encode("utf-8")


def _filing() -> bytes:
    return b"<html><body>Corporate governance update.</body></html>"


def _patch_download(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(url: str, *, user_agent: str, timeout_seconds: float = 20.0) -> bytes:
        assert "@" in user_agent
        assert timeout_seconds > 0
        return _submissions() if "submissions" in url else _filing()

    monkeypatch.setattr(scout_module, "download_sec_bytes", fake_download)


def test_scout_accepts_new_korea_date_before_utc_midnight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_download(monkeypatch)
    result = capture_post_earnings_product_mix_scout(
        observed_date=OBSERVED_DATE,
        after_date=AFTER_DATE,
        user_agent="AlphaCycleLab research@example.com",
        output=tmp_path / "kst-boundary",
        captured_at=datetime(2026, 8, 14, 16, 0, tzinfo=UTC),
    )
    assert result["observed_date"] == "2026-08-15"
    assert result["filing_count"] == 1


def test_scout_rejects_before_observed_date_in_korea(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_download(monkeypatch)
    with pytest.raises(ValueError, match="Asia/Seoul"):
        capture_post_earnings_product_mix_scout(
            observed_date=OBSERVED_DATE,
            after_date=AFTER_DATE,
            user_agent="AlphaCycleLab research@example.com",
            output=tmp_path / "too-early",
            captured_at=datetime(2026, 8, 14, 14, 59, tzinfo=UTC),
        )
