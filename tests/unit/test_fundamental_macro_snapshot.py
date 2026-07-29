"""Tests for immutable fundamental and macro snapshots."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from alpha_cycle.data.research import RevisionPolicy
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroSnapshot,
    _json_value,
    write_fundamental_macro_snapshot,
)


def test_snapshot_writer_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    financials = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "metric": "IS:Revenue",
                "period_end": date(2025, 12, 31),
                "fiscal_period": "FY",
                "value": 100,
                "unit": "KRW",
                "available_date": date(2026, 3, 15),
                "retrieved_at": pd.Timestamp("2026-07-28T06:00:00Z"),
                "source": "opendart",
                "revision_id": "20260315000001",
                "revision_sequence": 0,
                "period_start": pd.NaT,
                "currency": "KRW",
            }
        ]
    )
    macro = pd.DataFrame(
        [
            {
                "series_id": "kr_base_rate",
                "observation_date": date(2026, 7, 1),
                "frequency": "M",
                "value": 2.5,
                "unit": "%",
                "available_date": date(2026, 7, 28),
                "retrieved_at": pd.Timestamp("2026-07-28T06:00:00Z"),
                "source": "ecos",
                "revision_id": "r1",
                "revision_sequence": 0,
            }
        ]
    )
    snapshot = FundamentalMacroSnapshot(
        captured_at=datetime(2026, 7, 28, 6, tzinfo=UTC),
        evaluation_date=date(2026, 7, 28),
        revision_policy=RevisionPolicy.LATEST_KNOWN,
        financials=financials,
        disclosures=pd.DataFrame(
            columns=[
                "ticker",
                "corp_code",
                "corp_name",
                "rcept_no",
                "report_name",
                "receipt_date",
                "corp_class",
                "is_correction",
            ]
        ),
        macro=macro,
        raw_opendart={"ok": True},
        raw_ecos={"ok": True},
        market_snapshot_id="a" * 64,
        warnings=("example warning",),
    )
    first = write_fundamental_macro_snapshot(tmp_path, snapshot)
    second = write_fundamental_macro_snapshot(tmp_path, snapshot)
    assert first == second
    assert len(first) == 6
    manifest = json.loads(first[0].read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == snapshot.snapshot_id
    assert manifest["market_snapshot_id"] == "a" * 64
    assert manifest["availability_policy"]["ecos"] == "korea_retrieval_date_conservative"
    assert manifest["research_mode"] == "live_endpoint_filtered"
    assert manifest["historical_revision_archive_complete"] is False
    assert manifest["warnings"] == ["example warning"]
    assert manifest["order_api_enabled"] is False


def test_json_value_handles_numpy_scalars_and_missing_values() -> None:
    assert _json_value(np.int64(3)) == 3
    assert _json_value(np.bool_(True)) is True
    assert _json_value(np.float64(2.5)) == 2.5
    assert _json_value(np.float64(np.nan)) is None
