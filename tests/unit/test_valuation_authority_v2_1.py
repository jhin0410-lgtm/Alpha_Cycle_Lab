from __future__ import annotations

import hashlib
import json
from dataclasses import replace
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
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroSnapshot,
    write_fundamental_macro_snapshot,
)
from alpha_cycle.intelligence.market import (
    MarketIntelligenceSnapshot,
    write_market_intelligence_snapshot,
)
from alpha_cycle.intelligence.technical import calculate_technical_features
from alpha_cycle.providers.tossinvest import Candle, MarketPrice
from alpha_cycle.valuation_authority_v2_1 import (
    AuthorityClass,
    EligibilityStatus,
    ScenarioLabel,
    ValuationAuthorityError,
    ValuationMethod,
    build_valuation_authority,
    persist_valuation_authority,
    replay_persisted_valuation_authority,
    revalidate_persisted_valuation_authority,
)
from alpha_cycle.valuation_authority_v2_1_cli import main as authority_cli_main

CAPTURED = datetime(2026, 8, 25, 7, 0, tzinfo=UTC)


def _market() -> MarketIntelligenceSnapshot:
    source_time = CAPTURED - timedelta(hours=1)
    prices = tuple(
        MarketPrice(symbol=ticker, timestamp=source_time, last_price=price, currency="KRW")
        for ticker, price in (
            ("000660", Decimal("1647000")),
            ("005930", Decimal("273500")),
        )
    )
    candles: list[Candle] = []
    for ticker, base in (("000660", Decimal("1600000")), ("005930", Decimal("270000"))):
        for index in range(21):
            close = base + Decimal(index)
            candles.append(
                Candle(
                    symbol=ticker,
                    timestamp=source_time - timedelta(days=21 - index),
                    open_price=close,
                    high_price=close + 1,
                    low_price=close - 1,
                    close_price=close,
                    volume=Decimal(1000 + index),
                    currency="KRW",
                    interval="1d",
                    adjusted=True,
                )
            )
    ordered = tuple(sorted(candles, key=lambda item: (item.symbol, item.timestamp)))
    features = tuple(
        calculate_technical_features(tuple(row for row in ordered if row.symbol == ticker))
        for ticker in ("000660", "005930")
    )
    return MarketIntelligenceSnapshot(
        captured_at=source_time,
        provider="tossinvest-readonly",
        interval="1d",
        adjusted=True,
        prices=prices,
        candles=ordered,
        features=features,
        raw_prices={"writer_backed": True},
        raw_candles={"000660": {}, "005930": {}},
    )


def _research(market_id: str) -> FundamentalMacroSnapshot:
    rows = []
    values = {
        "000660": (42_947_902_000_000, 120_666_751_000_000, 14_923_766_000_000),
        "005930": (45_206_805_000_000, 436_320_337_000_000, 57_856_378_000_000),
    }
    metrics = (
        "CIS:ifrs-full_ProfitLoss#29",
        "BS:ifrs-full_Equity#32",
        "BS:ifrs-full_CashAndCashEquivalents#9",
    )
    for ticker, actuals in values.items():
        for metric, value in zip(metrics, actuals, strict=True):
            rows.append(
                {
                    "ticker": ticker,
                    "metric": metric,
                    "period_end": "2025-12-31",
                    "fiscal_period": "FY",
                    "value": value,
                    "unit": "KRW",
                    "available_date": "2026-03-17",
                    "retrieved_at": (CAPTURED - timedelta(minutes=30)).isoformat(),
                    "source": "opendart",
                    "revision_id": f"{ticker}-{metric}",
                    "revision_sequence": 0,
                }
            )
    financials = validate_financial_statements(pd.DataFrame(rows))
    macro = validate_macro_series(
        pd.DataFrame(
            [
                {
                    "series_id": "kr_base_rate",
                    "observation_date": "2026-08-24",
                    "frequency": "D",
                    "available_date": "2026-08-25",
                    "retrieved_at": (CAPTURED - timedelta(minutes=30)).isoformat(),
                    "source": "ecos",
                    "revision_id": "rate-1",
                    "revision_sequence": 0,
                    "value": 2.5,
                    "unit": "%",
                }
            ]
        )
    )
    return FundamentalMacroSnapshot(
        captured_at=CAPTURED - timedelta(minutes=20),
        evaluation_date=date(2026, 8, 25),
        revision_policy=RevisionPolicy.LATEST_KNOWN,
        financials=financials,
        disclosures=pd.DataFrame(
            [
                {
                    "ticker": "000660",
                    "receipt_date": date(2026, 3, 17),
                    "rcept_no": "20260317000001",
                    "is_correction": False,
                },
                {
                    "ticker": "005930",
                    "receipt_date": date(2026, 3, 10),
                    "rcept_no": "20260310000001",
                    "is_correction": False,
                },
            ]
        ),
        macro=macro,
        raw_opendart={"writer_backed": True},
        raw_ecos={"writer_backed": True},
        market_snapshot_id=market_id,
    )


def _sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research)[0].parent
    legacy = tmp_path / "legacy" / f"20260825T063000000000Z__{'a' * 12}"
    legacy.mkdir(parents=True)
    snapshot_id = "a" * 64
    files = [
        "shares.csv",
        "security_values.csv",
        "financial_history.csv",
        "valuation_metrics.csv",
        "raw_valuation.json",
    ]
    for name in files:
        (legacy / name).write_text(
            "{}" if name.endswith(".json") else "ticker\n000660\n005930\n", encoding="utf-8"
        )
    (legacy / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "captured_at": (CAPTURED - timedelta(minutes=10)).isoformat(),
                "evaluation_date": "2026-08-25",
                "research_snapshot_id": research.snapshot_id,
                "market_snapshot_id": market.snapshot_id,
                "symbols": ["000660", "005930"],
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return market_dir, research_dir, legacy


def _artifact(tmp_path: Path, ticker: str = "000660"):
    market, research, legacy = _sources(tmp_path)
    artifact = build_valuation_authority(
        market_directory=market,
        research_directory=research,
        legacy_valuation_directory=legacy,
        security_id=ticker,
        captured_at=CAPTURED,
    )
    return artifact, market, research, legacy


def _rewrite(path: Path, mutate) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _persist(artifact, output: Path, market: Path, research: Path, legacy: Path) -> Path:
    return persist_valuation_authority(
        artifact,
        output_root=output,
        market_directory=market,
        research_directory=research,
        legacy_valuation_directory=legacy,
    )


def test_writer_backed_actuals_and_price_replay_without_valuation_promotion(tmp_path: Path) -> None:
    artifact, _, _, _ = _artifact(tmp_path)
    inputs = {item.role: item for item in artifact.inputs}
    assert inputs["current_price"].value == 1_647_000
    assert inputs["trailing_net_income"].value == 42_947_902_000_000
    assert inputs["book_equity"].authority_class is AuthorityClass.AUTHORITATIVE_SOURCE
    assert (
        inputs["cash_and_cash_equivalents"].authority_class is AuthorityClass.AUTHORITATIVE_SOURCE
    )
    assert (
        inputs["share_count"].authority_class is AuthorityClass.REPLAYABLE_SEMANTICALLY_INSUFFICIENT
    )
    assert inputs["share_count"].value is None


@pytest.mark.parametrize("ticker,price", [("000660", 1_647_000), ("005930", 273_500)])
def test_real_security_price_binding(tmp_path: Path, ticker: str, price: int) -> None:
    artifact, _, _, _ = _artifact(tmp_path, ticker)
    assert next(item for item in artifact.inputs if item.role == "current_price").value == price


def test_every_method_has_an_explicit_fail_closed_eligibility_gate(tmp_path: Path) -> None:
    artifact, _, _, _ = _artifact(tmp_path)
    assert {item.method for item in artifact.methods} == set(ValuationMethod)
    assert all(item.status is EligibilityStatus.BLOCKED for item in artifact.methods)
    assert all(item.blockers for item in artifact.methods)
    assert artifact.payload_without_id()["eligible_methods"] == []


def test_trailing_and_forward_pe_remain_structurally_distinct(tmp_path: Path) -> None:
    artifact, _, _, _ = _artifact(tmp_path)
    methods = {item.method: item for item in artifact.methods}
    assert methods[ValuationMethod.TRAILING_PE].blockers == (
        "valuation_share_count_authority_missing",
    )
    assert methods[ValuationMethod.FORWARD_PE].blockers == ("forward_estimate_authority_missing",)


def test_scenarios_are_typed_complete_and_probability_free(tmp_path: Path) -> None:
    artifact, _, _, _ = _artifact(tmp_path)
    assert tuple(item.label for item in artifact.scenarios) == tuple(ScenarioLabel)
    assert all(item.implied_value_per_share is None for item in artifact.scenarios)
    assert all(item.blockers for item in artifact.scenarios)
    assert artifact.payload_without_id()["probabilities_available"] is False
    assert artifact.payload_without_id()["probability_weighted_expected_return_available"] is False


def test_price_implied_payoff_and_target_authority_remain_blocked(tmp_path: Path) -> None:
    payload = _artifact(tmp_path)[0].payload_without_id()
    assert payload["price_implied_requirement_authority_established"] is False
    assert payload["payoff_surface_authority_established"] is False
    assert payload["target_price_authority_established"] is False
    assert payload["market_consensus_authority_established"] is False


def test_persist_replay_and_upstream_revalidation_round_trip(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    directory = _persist(artifact, tmp_path / "authority", market, research, legacy)
    assert replay_persisted_valuation_authority(directory) == artifact
    assert (
        revalidate_persisted_valuation_authority(
            directory,
            market_directory=market,
            research_directory=research,
            legacy_valuation_directory=legacy,
        )
        == artifact
    )


def test_modified_share_source_changes_exact_content_lineage(tmp_path: Path) -> None:
    original, market, research, legacy = _artifact(tmp_path)
    (legacy / "shares.csv").write_text("ticker,issued_shares\n000660,1\n", encoding="utf-8")
    changed = build_valuation_authority(
        market_directory=market,
        research_directory=research,
        legacy_valuation_directory=legacy,
        security_id="000660",
        captured_at=CAPTURED,
    )
    assert changed.legacy_valuation_content_id != original.legacy_valuation_content_id
    assert changed.artifact_id != original.artifact_id
    assert next(item for item in changed.inputs if item.role == "share_count").value is None


def test_forged_authority_json_fails_digest_before_it_can_self_authorize(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    directory = _persist(artifact, tmp_path / "authority", market, research, legacy)
    _rewrite(
        directory / "authority.json",
        lambda value: value.__setitem__("share_count_authority_established", True),
    )
    with pytest.raises(ValuationAuthorityError, match="digest"):
        replay_persisted_valuation_authority(directory)


def test_caller_constructed_self_consistent_authority_cannot_be_persisted(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    inputs = tuple(
        replace(item, value=1.0) if item.role == "current_price" else item
        for item in artifact.inputs
    )
    forged = replace(artifact, inputs=inputs)
    assert forged.artifact_id != artifact.artifact_id
    with pytest.raises(ValuationAuthorityError, match="caller-created"):
        _persist(forged, tmp_path / "authority", market, research, legacy)


def test_unknown_field_tamper_with_updated_file_hash_remains_noncanonical(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    directory = _persist(artifact, tmp_path / "authority", market, research, legacy)
    _rewrite(directory / "authority.json", lambda value: value.__setitem__("trusted", True))
    content = (directory / "authority.json").read_bytes()
    _rewrite(
        directory / "manifest.json",
        lambda value: value["files"].__setitem__(
            "authority.json", hashlib.sha256(content).hexdigest()
        ),
    )
    with pytest.raises(ValuationAuthorityError, match="fields"):
        replay_persisted_valuation_authority(directory)


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda value: value.__setitem__("market_snapshot_id", "b" * 64), "source generation"),
        (lambda value: value.__setitem__("research_snapshot_id", "b" * 64), "source generation"),
        (lambda value: value.__setitem__("evaluation_date", "2026-08-24"), "evaluation date"),
        (lambda value: value.__setitem__("symbols", ["005930"]), "does not contain"),
    ],
)
def test_legacy_wrong_generation_date_or_security_is_rejected(
    tmp_path: Path, mutation, message: str
) -> None:
    market, research, legacy = _sources(tmp_path)
    _rewrite(legacy / "manifest.json", mutation)
    with pytest.raises(ValuationAuthorityError, match=message):
        build_valuation_authority(
            market_directory=market,
            research_directory=research,
            legacy_valuation_directory=legacy,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_future_authority_capture_and_unknown_security_fail_closed(tmp_path: Path) -> None:
    market, research, legacy = _sources(tmp_path)
    with pytest.raises(ValuationAuthorityError, match="precede source"):
        build_valuation_authority(
            market_directory=market,
            research_directory=research,
            legacy_valuation_directory=legacy,
            security_id="000660",
            captured_at=CAPTURED - timedelta(hours=2),
        )
    with pytest.raises(ValuationAuthorityError, match="exactly one"):
        build_valuation_authority(
            market_directory=market,
            research_directory=research,
            legacy_valuation_directory=None,
            security_id="999999",
            captured_at=CAPTURED,
        )


def test_market_price_after_evaluation_date_is_rejected(tmp_path: Path) -> None:
    market = _market()
    future_prices = tuple(
        replace(item, timestamp=datetime(2026, 8, 26, 0, 1, tzinfo=UTC)) for item in market.prices
    )
    future_market = replace(
        market,
        captured_at=datetime(2026, 8, 26, 0, 2, tzinfo=UTC),
        prices=future_prices,
    )
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", future_market)[0].parent
    research = _research(future_market.snapshot_id)
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research)[0].parent
    with pytest.raises(ValuationAuthorityError, match="after the evaluation date"):
        build_valuation_authority(
            market_directory=market_dir,
            research_directory=research_dir,
            legacy_valuation_directory=None,
            security_id="000660",
            captured_at=datetime(2026, 8, 26, 0, 3, tzinfo=UTC),
        )


def test_future_financial_actual_cannot_enter_trailing_valuation(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    original = _research(market.snapshot_id)
    future_financials = original.financials.copy()
    future_financials["available_date"] = date(2026, 8, 26)
    future_financials["retrieved_at"] = pd.Timestamp("2026-08-26T00:01:00+00:00")
    future_research = replace(
        original,
        captured_at=datetime(2026, 8, 26, 0, 2, tzinfo=UTC),
        financials=future_financials,
    )
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", future_research)[
        0
    ].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        legacy_valuation_directory=None,
        security_id="000660",
        captured_at=datetime(2026, 8, 26, 0, 3, tzinfo=UTC),
    )
    inputs = {item.role: item for item in artifact.inputs}
    assert inputs["trailing_net_income"].value is None
    assert inputs["trailing_net_income"].authority_class is AuthorityClass.UNSUPPORTED
    assert inputs["book_equity"].value is None


def test_price_mutation_is_detected_by_upstream_replay(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    directory = _persist(artifact, tmp_path / "authority", market, research, legacy)
    _rewrite(
        directory / "authority.json", lambda value: value["inputs"][3].__setitem__("value", 1.0)
    )
    with pytest.raises(ValuationAuthorityError):
        replay_persisted_valuation_authority(directory)
    assert market.is_dir() and research.is_dir() and legacy.is_dir()


def test_raw_market_or_research_mutation_is_rejected(tmp_path: Path) -> None:
    market, research, legacy = _sources(tmp_path)
    (market / "raw_prices.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        build_valuation_authority(
            market_directory=market,
            research_directory=research,
            legacy_valuation_directory=legacy,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_wrong_market_research_generation_is_rejected(tmp_path: Path) -> None:
    market, _, legacy = _sources(tmp_path)
    wrong_research = _research("b" * 64)
    wrong_dir = write_fundamental_macro_snapshot(tmp_path / "wrong-research", wrong_research)[
        0
    ].parent
    with pytest.raises(ValuationAuthorityError, match="generation mismatch"):
        build_valuation_authority(
            market_directory=market,
            research_directory=wrong_dir,
            legacy_valuation_directory=legacy,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_duplicate_identity_conflict_and_symlink_escape_fail_closed(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    repository = tmp_path / "authority"
    directory = _persist(artifact, repository, market, research, legacy)
    (directory / "authority.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValuationAuthorityError):
        _persist(artifact, repository, market, research, legacy)
    link = tmp_path / "authority-link"
    try:
        link.symlink_to(repository, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValuationAuthorityError, match="plain directory"):
        _persist(artifact, link, market, research, legacy)


def test_no_legacy_share_source_stays_class_e(tmp_path: Path) -> None:
    _, market, research, _ = _artifact(tmp_path)
    artifact = build_valuation_authority(
        market_directory=market,
        research_directory=research,
        legacy_valuation_directory=None,
        security_id="000660",
        captured_at=CAPTURED,
    )
    share = next(item for item in artifact.inputs if item.role == "share_count")
    assert share.authority_class is AuthorityClass.UNSUPPORTED
    assert share.source_evidence_id is None


def test_scenario_wrong_horizon_and_fabricated_probability_are_rejected(tmp_path: Path) -> None:
    artifact, _, _, _ = _artifact(tmp_path)
    with pytest.raises(ValueError, match="horizon"):
        replace(artifact.scenarios[0], horizon_trading_days=30)
    payload = artifact.scenarios[0].payload()
    assert payload["probability"] is None
    assert payload["target_price_claimed"] is False


def test_cli_records_both_real_security_acceptances(tmp_path: Path, capsys) -> None:
    market, research, legacy = _sources(tmp_path)
    result = authority_cli_main(
        [
            "--market-snapshot",
            str(market),
            "--research-snapshot",
            str(research),
            "--legacy-valuation-snapshot",
            str(legacy),
            "--security",
            "005930",
            "--security",
            "000660",
            "--captured-at",
            CAPTURED.isoformat(),
            "--output",
            str(tmp_path / "acceptance"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert [item["security_id"] for item in payload["artifacts"]] == ["000660", "005930"]
    assert all(item["eligible_methods"] == [] for item in payload["artifacts"])
    assert all(item["probabilities_available"] is False for item in payload["artifacts"])


def test_cli_fails_closed_for_unknown_security(tmp_path: Path, capsys) -> None:
    market, research, legacy = _sources(tmp_path)
    result = authority_cli_main(
        [
            "--market-snapshot",
            str(market),
            "--research-snapshot",
            str(research),
            "--legacy-valuation-snapshot",
            str(legacy),
            "--security",
            "999999",
            "--captured-at",
            CAPTURED.isoformat(),
            "--output",
            str(tmp_path / "acceptance"),
        ]
    )
    assert result == 2
    assert "exactly one trusted market price" in capsys.readouterr().err
