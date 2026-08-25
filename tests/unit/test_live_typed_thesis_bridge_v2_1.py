from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.data.research import (
    RevisionPolicy,
    validate_financial_statements,
    validate_macro_series,
)
from alpha_cycle.intelligence.decision_thesis_v2 import EpistemicStatus, ThesisStatus
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroSnapshot,
    write_fundamental_macro_snapshot,
)
from alpha_cycle.intelligence.market import (
    MarketIntelligenceSnapshot,
    write_market_intelligence_snapshot,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.technical import calculate_technical_features
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.live_typed_research_runner_v2_1 import (
    _persist_result,
    run_live_typed_research_round,
)
from alpha_cycle.live_typed_source_manifest_v2_1 import freeze_live_typed_source_manifest
from alpha_cycle.live_typed_thesis_bridge_v2_1 import produce_source_backed_theses
from alpha_cycle.providers.tossinvest import Candle, MarketPrice
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state


def _persist_sources(
    root: Path,
    *,
    research_market_snapshot_id: str | None = None,
    future_financial_retrieval: bool = False,
    tickers: tuple[str, ...] = ("000660", "005930"),
    financial_source: str = "opendart",
    evaluation_date: date = date(2026, 8, 25),
) -> tuple[Path, Path, datetime]:
    captured_at = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    price_values = {"000660": Decimal("250000"), "005930": Decimal("80000")}
    prices = tuple(
        MarketPrice(ticker, captured_at - timedelta(minutes=1), price_values[ticker], "KRW")
        for ticker in tickers
    )
    candles: list[Candle] = []
    features = []
    candle_bases = {"000660": Decimal("200000"), "005930": Decimal("70000")}
    for symbol in tickers:
        base = candle_bases[symbol]
        symbol_candles = tuple(
            Candle(
                symbol=symbol,
                timestamp=captured_at - timedelta(days=21 - index),
                open_price=base + index - 1,
                high_price=base + index + 1,
                low_price=base + index - 2,
                close_price=base + index,
                volume=Decimal(1000 + index),
                currency="KRW",
                interval="1d",
                adjusted=True,
            )
            for index in range(21)
        )
        candles.extend(symbol_candles)
        features.append(calculate_technical_features(symbol_candles))
    market = MarketIntelligenceSnapshot(
        captured_at=captured_at,
        provider="tossinvest-readonly",
        interval="1d",
        adjusted=True,
        prices=prices,
        candles=tuple(sorted(candles, key=lambda item: (item.symbol, item.timestamp))),
        features=tuple(features),
        raw_prices={"source": "market"},
        raw_candles={ticker: {"count": 21} for ticker in tickers},
    )
    market_dir = write_market_intelligence_snapshot(root / "market", market)[0].parent

    financials = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "metric": metric,
                "period_end": "2025-12-31",
                "fiscal_period": "FY",
                "available_date": "2026-03-20",
                "retrieved_at": (
                    "2026-08-25T07:05:00+00:00"
                    if future_financial_retrieval
                    else "2026-08-25T06:05:00+00:00"
                ),
                "source": financial_source,
                "revision_id": f"{ticker}-{metric}-2025",
                "revision_sequence": 0,
                "value": value,
                "unit": "KRW",
            }
            for ticker, multiplier in (
                (ticker, 2 if ticker == "000660" else 1) for ticker in tickers
            )
            for metric, value in (
                ("revenue", 1000 * multiplier),
                ("operating_income", 200 * multiplier),
            )
        ]
    )
    research = FundamentalMacroSnapshot(
        captured_at=captured_at + timedelta(minutes=5),
        evaluation_date=evaluation_date,
        revision_policy=RevisionPolicy.LATEST_KNOWN,
        financials=validate_financial_statements(financials),
        disclosures=pd.DataFrame(
            [
                {
                    "ticker": ticker,
                    "receipt_date": date(2026, 3, 20),
                    "rcept_no": ticker,
                    "is_correction": False,
                }
                for ticker in tickers
            ]
        ),
        macro=validate_macro_series(pd.DataFrame(
            [
                {
                    "series_id": "kr_base_rate",
                    "observation_date": "2026-08-24",
                    "frequency": "D",
                    "available_date": "2026-08-25",
                    "retrieved_at": "2026-08-25T06:05:00+00:00",
                    "source": "ecos",
                    "revision_id": "kr-base-rate-20260824",
                    "revision_sequence": 0,
                    "value": 2.5,
                    "unit": "%",
                }
            ]
        )),
        raw_opendart={"source": "opendart"},
        raw_ecos={"source": "ecos"},
        market_snapshot_id=(
            market.snapshot_id
            if research_market_snapshot_id is None
            else research_market_snapshot_id
        ),
    )
    research_dir = write_fundamental_macro_snapshot(root / "research", research)[0].parent
    return market_dir, research_dir, captured_at


def test_writer_backed_sources_produce_two_evidence_gated_theses(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    cutoff = captured_at + timedelta(minutes=20)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=cutoff,
        frozen_at=captured_at + timedelta(minutes=10),
    )

    receipt = produce_source_backed_theses(
        manifest,
        artifact_root=tmp_path,
        security_ids=("000660", "005930"),
        horizon_trading_days=120,
        captured_at=manifest.research_cutoff_at,
    )

    assert not receipt.blockers
    assert tuple(item.security_id for item in receipt.theses) == ("000660", "005930")
    assert all(item.status is ThesisStatus.EVIDENCE_GATED for item in receipt.theses)
    assert all(item.captured_at <= cutoff for item in receipt.theses)
    assert all(
        claim.epistemic_status is EpistemicStatus.OBSERVED_FACT
        for thesis in receipt.theses
        for claim in thesis.claims
    )
    assert all(path.is_file() for path in receipt.thesis_paths)
    assert all(not thesis.catalysts for thesis in receipt.theses)
    assert all(not thesis.forecast_refs for thesis in receipt.theses)


def test_thesis_capture_time_is_canonical_for_repeated_production(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(minutes=20),
        frozen_at=captured_at + timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="must equal the frozen research_cutoff_at"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660",),
            horizon_trading_days=120,
            captured_at=manifest.research_cutoff_at - timedelta(microseconds=1),
        )


def test_missing_official_financial_fact_becomes_structured_blocker(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    financials_path = research_dir / "financials.csv"
    financials = pd.read_csv(financials_path)
    financials = financials.loc[financials["ticker"].astype(str).str.zfill(6) != "005930"]
    financials.to_csv(financials_path, index=False)

    cutoff = captured_at + timedelta(minutes=20)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=cutoff,
        frozen_at=captured_at + timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="financial row count mismatch"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660", "005930"),
            horizon_trading_days=120,
            captured_at=manifest.research_cutoff_at,
        )


def test_mixed_market_research_generation_is_rejected(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(
        tmp_path,
        research_market_snapshot_id="f" * 64,
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(minutes=20),
        frozen_at=captured_at + timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="mixed source generations"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660", "005930"),
            horizon_trading_days=120,
            captured_at=manifest.research_cutoff_at,
        )


def test_future_market_observation_cannot_be_promoted(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(minutes=20),
        frozen_at=captured_at + timedelta(minutes=10),
    )
    prices_path = market_dir / "prices.csv"
    prices = pd.read_csv(prices_path)
    prices.loc[0, "timestamp"] = (captured_at + timedelta(hours=1)).isoformat()
    prices.to_csv(prices_path, index=False)

    with pytest.raises(ValueError, match="source file bytes changed during replay"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660", "005930"),
            horizon_trading_days=120,
            captured_at=manifest.research_cutoff_at,
        )


def test_market_observation_after_evaluation_date_cannot_be_promoted(
    tmp_path: Path,
) -> None:
    evaluation_date = date(2026, 8, 24)
    market_dir, research_dir, captured_at = _persist_sources(
        tmp_path,
        evaluation_date=evaluation_date,
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=evaluation_date,
        research_cutoff_at=captured_at + timedelta(minutes=20),
        frozen_at=captured_at + timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="manifest evaluation_date"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660",),
            horizon_trading_days=120,
            captured_at=manifest.research_cutoff_at,
        )


def test_one_command_runner_reaches_observatory_with_honest_package_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    cutoff = captured_at + timedelta(minutes=20)

    receipt = run_live_typed_research_round(
        artifact_root=tmp_path,
        mode=ResearchRoundMode.PROSPECTIVE,
        request_id="live-v2-1-acceptance",
        run_id="live-v2-1-run",
        round_id="live-v2-1-round",
        processed_at=cutoff + timedelta(minutes=1),
        security_ids=("000660", "005930"),
        horizon_trading_days=120,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Writer-backed acceptance for 000660 and 005930.",
        market_source_directory=market_dir,
        research_source_directory=research_dir,
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=cutoff,
    )

    payload = receipt.payload()
    assert receipt.result_path.is_file()
    assert payload["observatory_ledger_snapshot_id"]
    assert payload["network_collection_enabled"] is False
    assert payload["target_price_enabled"] is False
    assert payload["optimal_position_size_enabled"] is False
    assert payload["assembly"] is not None
    assert payload["ready"] is False
    assert not (tmp_path / "opportunity_set_v2_1").exists()
    assert not (tmp_path / "research_round_v2_1").exists()

    def reject_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("REPLAY attempted network access")

    monkeypatch.setattr("socket.create_connection", reject_network)
    replay = run_live_typed_research_round(
        artifact_root=tmp_path,
        mode=ResearchRoundMode.REPLAY,
        request_id="live-v2-1-replay",
        run_id="live-v2-1-replay-run",
        round_id="live-v2-1-replay-round",
        processed_at=cutoff + timedelta(minutes=2),
        security_ids=("000660", "005930"),
        horizon_trading_days=120,
        requested_lane=UnderwritingLane.DEEP,
        request_text="No-network frozen replay acceptance.",
        manifest_path=Path(str(payload["source_manifest_path"])),
    )
    assert replay.payload()["mode"] == "replay"
    assert replay.payload()["network_collection_enabled"] is False
    observatory = load_latest_observatory_state(tmp_path)
    assert observatory is not None
    replay_request = next(
        item for item in observatory.ledger.requests if item.request_id == "live-v2-1-replay"
    )
    assert replay_request.requested_at == cutoff + timedelta(minutes=2, microseconds=-2)

    for replay_dates in (
        {"evaluation_date": date(2026, 8, 25)},
        {"research_cutoff_at": cutoff},
    ):
        with pytest.raises(ValueError, match="takes evaluation_date and research_cutoff_at"):
            run_live_typed_research_round(
                artifact_root=tmp_path,
                mode=ResearchRoundMode.REPLAY,
                request_id="ignored-replay-date",
                run_id="ignored-replay-date-run",
                round_id="ignored-replay-date-round",
                processed_at=cutoff + timedelta(minutes=3),
                security_ids=("000660", "005930"),
                horizon_trading_days=120,
                requested_lane=UnderwritingLane.DEEP,
                request_text="Replay dates must come only from the manifest.",
                manifest_path=Path(str(payload["source_manifest_path"])),
                **replay_dates,
            )


def test_missing_requested_ticker_is_a_structured_source_blocker(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    cutoff = captured_at + timedelta(minutes=20)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=cutoff,
        frozen_at=captured_at + timedelta(minutes=10),
    )

    receipt = produce_source_backed_theses(
        manifest,
        artifact_root=tmp_path,
        security_ids=("999999",),
        horizon_trading_days=120,
        captured_at=manifest.research_cutoff_at,
    )

    assert not receipt.theses
    assert [item.code for item in receipt.blockers] == ["live_market_observation_missing"]


def test_future_financial_retrieval_cannot_be_promoted(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(
        tmp_path,
        future_financial_retrieval=True,
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(hours=2),
        frozen_at=captured_at + timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="financial observation cannot follow"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660",),
            horizon_trading_days=120,
            captured_at=manifest.research_cutoff_at,
        )


def test_non_opendart_financial_rows_cannot_be_labeled_official(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(
        tmp_path,
        financial_source="csv",
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(minutes=20),
        frozen_at=captured_at + timedelta(minutes=10),
    )

    receipt = produce_source_backed_theses(
        manifest,
        artifact_root=tmp_path,
        security_ids=("000660",),
        horizon_trading_days=120,
        captured_at=manifest.research_cutoff_at,
    )

    assert not receipt.theses
    assert [item.code for item in receipt.blockers] == [
        "live_official_financial_fact_missing"
    ]


def test_runner_does_not_fall_back_to_stale_thesis_after_source_blocker(
    tmp_path: Path,
) -> None:
    old_market, old_research, captured_at = _persist_sources(tmp_path / "old")
    cutoff = captured_at + timedelta(minutes=20)
    old_manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": old_market, "research": old_research},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=cutoff,
        frozen_at=captured_at + timedelta(minutes=10),
    )
    old = produce_source_backed_theses(
        old_manifest,
        artifact_root=tmp_path,
        security_ids=("005930",),
        horizon_trading_days=120,
        captured_at=old_manifest.research_cutoff_at,
    )
    assert old.theses
    current_market, current_research, _ = _persist_sources(
        tmp_path / "current",
        tickers=("000660",),
    )

    receipt = run_live_typed_research_round(
        artifact_root=tmp_path,
        mode=ResearchRoundMode.PROSPECTIVE,
        request_id="blocked-current-source",
        run_id="blocked-current-source-run",
        round_id="blocked-current-source-round",
        processed_at=cutoff + timedelta(minutes=1),
        security_ids=("005930",),
        horizon_trading_days=120,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Current source must not fall back to an older thesis.",
        market_source_directory=current_market,
        research_source_directory=current_research,
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=cutoff,
    )
    payload = receipt.payload()

    assert payload["exact_source_thesis_binding"] is False
    assert payload["preflight"]["blockers"][0]["code"] == (
        "source_backed_thesis_snapshot_missing"
    )
    assert payload["assembly"] is None
    assert payload["ready"] is False


def test_result_repository_symlink_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    repository = tmp_path / "live_typed_research_round_v2_1"
    try:
        os.symlink(outside, repository, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="repository cannot be a symlink"):
        _persist_result(tmp_path, {"safe": True})


def test_existing_result_artifact_symlink_is_rejected(tmp_path: Path) -> None:
    payload = {"safe": True}
    path = _persist_result(tmp_path, payload)
    outside = tmp_path / "outside-result.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    try:
        os.symlink(outside, path)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="result artifact cannot be a symlink"):
        _persist_result(tmp_path, payload)


def test_thesis_repository_symlink_is_rejected_before_persistence(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(minutes=20),
        frozen_at=captured_at + timedelta(minutes=10),
    )
    outside = tmp_path / "outside-theses"
    outside.mkdir()
    repository = tmp_path / "investment_thesis_v2_1"
    try:
        os.symlink(outside, repository, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="thesis repository cannot be a symlink"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660",),
            horizon_trading_days=120,
            captured_at=manifest.research_cutoff_at,
        )


def test_existing_thesis_artifact_symlink_is_rejected(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(minutes=20),
        frozen_at=captured_at + timedelta(minutes=10),
    )
    first = produce_source_backed_theses(
        manifest,
        artifact_root=tmp_path,
        security_ids=("000660",),
        horizon_trading_days=120,
        captured_at=manifest.research_cutoff_at,
    )
    path = first.thesis_paths[0]
    outside = tmp_path / "outside-thesis.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    try:
        os.symlink(outside, path)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="thesis artifact cannot be a symlink"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660",),
            horizon_trading_days=120,
            captured_at=manifest.research_cutoff_at,
        )
