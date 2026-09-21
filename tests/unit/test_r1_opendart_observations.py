from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from test_valuation_authority_v2_1 import CAPTURED, _research

from alpha_cycle.intelligence.fundamental_macro import write_fundamental_macro_snapshot
from alpha_cycle.intelligence.observable_universe import EvidenceMaturity
from alpha_cycle.intelligence.r1_opendart_observations import (
    OpenDartFieldSelection,
    load_opendart_universe,
)


def selection() -> OpenDartFieldSelection:
    return OpenDartFieldSelection(
        "000660", "memory_semiconductor", "reported_profit",
        "CIS:ifrs-full_ProfitLoss#29", date(2025, 12, 31), "FY",
    )


def load(path: Path, *, chosen=None, cutoff=CAPTURED):
    return load_opendart_universe(
        path, selections=(chosen or selection(),),
        universe_id="reported-actuals", version="1", cutoff_at=cutoff,
    )


def test_writer_replay_to_observation_preserves_exact_value_and_capture(tmp_path: Path) -> None:
    source = _research("a" * 64)
    directory = write_fundamental_macro_snapshot(tmp_path, source)[0].parent
    universe = load(directory)
    observation = universe.observations[0]
    assert observation.value == 42_947_902_000_000
    assert isinstance(observation.value, int)
    assert observation.available_at == source.captured_at
    assert observation.maturity is EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE
    assert observation.window == "FY:2025-12-31:thstrm_amount"
    assert load(directory).snapshot_id == universe.snapshot_id
    assert universe.members[0].required_dimensions == ("reported_profit",)


@pytest.mark.parametrize("field,value", [
    ("statement_basis", "OFS"),
    ("metric_id", "IS:ifrs-full_Revenue#1"),
    ("fiscal_period", "H1"),
    ("period_end", date(2024, 12, 31)),
    ("security_id", "123456"),
])
def test_selection_cannot_substitute_semantics(tmp_path: Path, field: str, value) -> None:
    directory = write_fundamental_macro_snapshot(tmp_path, _research("a" * 64))[0].parent
    with pytest.raises(ValueError):
        load(directory, chosen=replace(selection(), **{field: value}))


def test_recomputed_snapshot_hash_cannot_hide_changed_normalized_value(tmp_path: Path) -> None:
    source = _research("a" * 64)
    frame = source.financials.copy()
    frame.loc[frame["metric"].eq(selection().metric_id), "value"] = 123
    source = replace(source, financials=frame)
    directory = write_fundamental_macro_snapshot(tmp_path, source)[0].parent
    with pytest.raises(ValueError, match="differs from raw"):
        load(directory)


def test_raw_company_identity_must_match_selected_security(tmp_path: Path) -> None:
    source = _research("a" * 64)
    raw = copy.deepcopy(source.raw_opendart)
    raw["000660"]["financial"]["company"]["stock_code"] = "005930"
    directory = write_fundamental_macro_snapshot(
        tmp_path, replace(source, raw_opendart=raw)
    )[0].parent
    with pytest.raises(ValueError, match="company identity mismatch"):
        load(directory)


def test_source_cannot_be_backdated_to_filing_date(tmp_path: Path) -> None:
    source = _research("a" * 64)
    directory = write_fundamental_macro_snapshot(tmp_path, source)[0].parent
    with pytest.raises(ValueError, match="capture exceeds"):
        load(directory, cutoff=source.captured_at - timedelta(microseconds=1))


def test_duplicate_slots_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        load_opendart_universe(
            tmp_path, selections=(selection(), selection()),
            universe_id="reported-actuals", version="1", cutoff_at=CAPTURED,
        )
