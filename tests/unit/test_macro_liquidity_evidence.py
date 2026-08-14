from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.macro_liquidity_evidence import (
    build_macro_liquidity_evidence,
    load_macro_liquidity_registry,
)

REGISTRY = Path("config/macro_liquidity_sources.yaml")


def _csv(series_id: str, values: list[tuple[str, float]]) -> bytes:
    rows = [f"DATE,{series_id}"] + [f"{day},{value}" for day, value in values]
    return ("\n".join(rows) + "\n").encode()


def test_macro_liquidity_registry_keeps_distinct_official_transmission_legs() -> None:
    specs = load_macro_liquidity_registry(REGISTRY)
    assert {spec.series_id for spec in specs} == {
        "DFII10",
        "DTWEXBGS",
        "NFCI",
        "WALCL",
        "WRESBAL",
    }
    assert all(spec.primary_official_system for spec in specs)
    assert len({spec.dimension for spec in specs}) == 5
    assert all(spec.url.startswith("https://fred.stlouisfed.org/") for spec in specs)


def test_macro_liquidity_evidence_uses_official_nfci_sign_without_composite_score() -> None:
    specs = load_macro_liquidity_registry(REGISTRY)
    payloads: dict[str, bytes] = {}
    for spec in specs:
        base = 1.0
        if spec.series_id == "DFII10":
            base = 1.5
        elif spec.series_id == "DTWEXBGS":
            base = 120.0
        elif spec.series_id == "NFCI":
            base = 0.2
        elif spec.series_id == "WALCL":
            base = 6_700_000.0
        elif spec.series_id == "WRESBAL":
            base = 3_000_000.0
        values = [
            ((pd.Timestamp("2026-07-01") + pd.Timedelta(days=index)).date().isoformat(), base + index)
            for index in range(25)
        ]
        payloads[spec.url] = _csv(spec.series_id, values)

    evidence = build_macro_liquidity_evidence(
        specs,
        lambda url: payloads[url],
        evaluation_date=date(2026, 8, 14),
    )
    assert evidence.decision_score_enabled is False
    assert evidence.composite_liquidity_score_enabled is False
    assert evidence.forecast_enabled is False
    assert evidence.causal_claim_enabled is False
    assert evidence.historical_vintage_certified is False
    assert evidence.point_in_time_backtest_eligible is False
    assert len(evidence.series) == 5

    nfci = evidence.series.loc[evidence.series["series_id"].eq("NFCI")].iloc[0]
    assert nfci["level_state"] == "tighter_than_average"
    dfii = evidence.series.loc[evidence.series["series_id"].eq("DFII10")].iloc[0]
    assert dfii["level_state"] == "level_only_no_universal_threshold"
    assert float(dfii["change_20_observations"]) == pytest.approx(20.0)


def test_macro_liquidity_excludes_future_observations() -> None:
    specs = load_macro_liquidity_registry(REGISTRY)
    payloads = {
        spec.url: _csv(
            spec.series_id,
            [("2026-08-13", 1.0), ("2026-08-14", 2.0), ("2026-08-15", 999.0)],
        )
        for spec in specs
    }
    evidence = build_macro_liquidity_evidence(
        specs,
        lambda url: payloads[url],
        evaluation_date=date(2026, 8, 14),
    )
    assert evidence.series["latest_value"].eq(2.0).all()
    assert evidence.series["latest_date"].astype(str).eq("2026-08-14").all()
