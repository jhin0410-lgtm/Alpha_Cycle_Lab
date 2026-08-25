from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

import alpha_cycle.valuation_authority_v2_1 as valuation_authority_module
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
from alpha_cycle.intelligence.valuation import (
    ValuationEvidenceSnapshot,
    write_valuation_evidence_snapshot,
)
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
        raw_prices={
            "result": [
                {
                    "symbol": item.symbol,
                    "timestamp": item.timestamp.isoformat(),
                    "lastPrice": str(item.last_price),
                    "currency": item.currency,
                }
                for item in prices
            ]
        },
        raw_candles={"000660": {}, "005930": {}},
    )


def _raw_opendart(financials: pd.DataFrame, *, fs_div: str = "CFS") -> dict[str, object]:
    raw: dict[str, object] = {}
    for ticker, group in financials.groupby("ticker", sort=True):
        rows: list[dict[str, object]] = []
        for normalized in group.to_dict(orient="records"):
            statement, account = str(normalized["metric"]).split(":", 1)
            account, _, order = account.partition("#")
            account, _, detail = account.partition(":")
            period_end = pd.Timestamp(normalized["period_end"]).date()
            rows.append(
                {
                    "stock_code": str(ticker),
                    "sj_div": statement,
                    "account_id": account,
                    "account_nm": account,
                    "account_detail": detail or "-",
                    "ord": order,
                    "thstrm_amount": str(normalized["value"]),
                    "rcept_no": str(normalized["revision_id"]),
                    "bsns_year": str(period_end.year),
                    "reprt_code": ("11011" if str(normalized["fiscal_period"]) == "FY" else ""),
                    "currency": "KRW",
                }
            )
        raw[str(ticker)] = {
            "request": {"fs_div": fs_div},
            "corp": {"stock_code": str(ticker)},
            "financial": {"financials": {"list": rows}},
        }
    return raw


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
                    "revision_id": ("20260317000635" if ticker == "000660" else "20260317000999"),
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
        raw_opendart=_raw_opendart(financials),
        raw_ecos={"writer_backed": True},
        market_snapshot_id=market_id,
    )


def _sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research)[0].parent
    shares = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "security_class": "common",
                "issued_shares": shares,
                "treasury_shares": 0,
            }
            for ticker, shares in (("000660", 100), ("005930", 200))
        ]
    )
    metrics = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "market_cap_complete": False,
                "valuation_score": None,
            }
            for ticker in ("000660", "005930")
        ]
    )
    legacy_snapshot = ValuationEvidenceSnapshot(
        captured_at=CAPTURED - timedelta(minutes=10),
        evaluation_date=date(2026, 8, 25),
        research_snapshot_id=research.snapshot_id,
        market_snapshot_id=market.snapshot_id,
        history_years=3,
        shares=shares,
        security_values=pd.DataFrame({"ticker": ["000660", "005930"]}),
        financial_history=pd.DataFrame({"ticker": ["000660", "005930"]}),
        valuation_metrics=metrics,
        raw_valuation={
            "source_research_snapshot_id": research.snapshot_id,
            "source_market_snapshot_id": market.snapshot_id,
        },
    )
    legacy = write_valuation_evidence_snapshot(tmp_path / "legacy", legacy_snapshot)[0].parent
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


def _replay(directory: Path, market: Path, research: Path, legacy: Path):
    return replay_persisted_valuation_authority(
        directory,
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
    assert inputs["book_equity"].currency == "KRW"
    assert (
        inputs["cash_and_cash_equivalents"].authority_class is AuthorityClass.AUTHORITATIVE_SOURCE
    )
    assert (
        inputs["share_count"].authority_class is AuthorityClass.REPLAYABLE_SEMANTICALLY_INSUFFICIENT
    )
    assert inputs["share_count"].value is None


def test_non_opendart_financial_rows_cannot_become_class_a(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    financials = research.financials.copy()
    financials["source"] = "untrusted_vendor"
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research",
        replace(research, financials=financials, raw_opendart=_raw_opendart(financials)),
    )[0].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        security_id="000660",
        captured_at=CAPTURED,
    )
    actuals = [
        item
        for item in artifact.inputs
        if item.role in {"trailing_net_income", "book_equity", "cash_and_cash_equivalents"}
    ]
    assert all(item.authority_class is AuthorityClass.UNSUPPORTED for item in actuals)


def test_non_krw_market_price_is_rejected(tmp_path: Path) -> None:
    market = _market()
    usd_market = replace(
        market,
        prices=tuple(replace(item, currency="USD") for item in market.prices),
    )
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", usd_market)[0].parent
    research = _research(usd_market.snapshot_id)
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research)[0].parent
    with pytest.raises(ValuationAuthorityError, match="denominated in KRW"):
        build_valuation_authority(
            market_directory=market_dir,
            research_directory=research_dir,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_unapproved_market_provider_is_rejected(tmp_path: Path) -> None:
    market = replace(_market(), provider="caller-supplied")
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research)[0].parent
    with pytest.raises(ValuationAuthorityError, match="provider is not approved"):
        build_valuation_authority(
            market_directory=market_dir,
            research_directory=research_dir,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_zero_market_price_is_rejected(tmp_path: Path) -> None:
    original = _market()
    market = replace(
        original,
        prices=tuple(replace(item, last_price=Decimal(0)) for item in original.prices),
    )
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research)[0].parent
    with pytest.raises(ValuationAuthorityError, match="strictly positive"):
        build_valuation_authority(
            market_directory=market_dir,
            research_directory=research_dir,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_stale_market_price_is_rejected(tmp_path: Path) -> None:
    original = _market()
    market = replace(
        original,
        prices=tuple(
            replace(item, timestamp=item.timestamp - timedelta(days=5)) for item in original.prices
        ),
    )
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research)[0].parent
    with pytest.raises(ValuationAuthorityError, match="stale"):
        build_valuation_authority(
            market_directory=market_dir,
            research_directory=research_dir,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_normalized_price_must_match_raw_tossinvest_capture(tmp_path: Path) -> None:
    original = _market()
    market = replace(
        original,
        prices=tuple(
            replace(item, last_price=item.last_price + Decimal(1)) for item in original.prices
        ),
    )
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research)[0].parent
    with pytest.raises(ValuationAuthorityError, match="differs from raw TossInvest"):
        build_valuation_authority(
            market_directory=market_dir,
            research_directory=research_dir,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_normalized_actual_must_match_raw_opendart_capture(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    financials = research.financials.copy()
    mask = financials["ticker"].astype(str).eq("000660") & financials["metric"].astype(
        str
    ).str.contains("ProfitLoss#")
    financials.loc[mask, "value"] = financials.loc[mask, "value"] + 1
    financials = validate_financial_statements(financials)
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research", replace(research, financials=financials)
    )[0].parent
    with pytest.raises(ValuationAuthorityError, match="differs from raw OpenDART"):
        build_valuation_authority(
            market_directory=market_dir,
            research_directory=research_dir,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_opendart_request_metadata_alone_cannot_authorize_actuals(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    request_only = {ticker: {"request": {"fs_div": "CFS"}} for ticker in ("000660", "005930")}
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research", replace(research, raw_opendart=request_only)
    )[0].parent
    with pytest.raises(ValuationAuthorityError, match="financial response is unavailable"):
        build_valuation_authority(
            market_directory=market_dir,
            research_directory=research_dir,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_ofs_statement_basis_cannot_be_published_as_cfs(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    raw = {ticker: {"request": {"fs_div": "OFS"}} for ticker in ("000660", "005930")}
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research", replace(research, raw_opendart=raw)
    )[0].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        security_id="000660",
        captured_at=CAPTURED,
    )
    actuals = [
        item
        for item in artifact.inputs
        if item.role in {"trailing_net_income", "book_equity", "cash_and_cash_equivalents"}
    ]
    assert all(item.statement_basis == "OFS" for item in actuals)
    assert all(item.blocker and item.blocker.endswith("basis_unsupported") for item in actuals)


def test_conflicting_opendart_basis_proofs_fail_closed(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    raw = {
        "000660": {
            "request": {"fs_div": "CFS"},
            "financial": {"financials": {"list": [{"fs_div": "OFS"}]}},
        }
    }
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research", replace(research, raw_opendart=raw)
    )[0].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        security_id="000660",
        captured_at=CAPTURED,
    )
    actuals = [
        item
        for item in artifact.inputs
        if item.role in {"trailing_net_income", "book_equity", "cash_and_cash_equivalents"}
    ]
    assert all(item.blocker and item.blocker.endswith("basis_missing") for item in actuals)


def test_canonical_opendart_metric_aliases_are_authoritative(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    aliases = {
        "CIS:ifrs-full_ProfitLoss#29": "CIS:dart_ProfitLoss",
        "BS:ifrs-full_Equity#32": "BS:자본총계",
        "BS:ifrs-full_CashAndCashEquivalents#9": "BS:현금및현금성자산",
    }
    financials = research.financials.copy()
    operating = (
        financials.loc[
            financials["ticker"].astype(str).eq("000660")
            & financials["metric"].astype(str).str.contains("ProfitLoss#")
        ]
        .iloc[0]
        .copy()
    )
    operating["metric"] = "CIS:ifrs-full_ProfitLossFromOperatingActivities"
    operating["value"] = 1
    operating["revision_id"] = "000660-operating-profit"
    financials = pd.concat([financials, pd.DataFrame([operating])], ignore_index=True)
    financials["metric"] = financials["metric"].replace(aliases)
    financials = validate_financial_statements(financials)
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research",
        replace(research, financials=financials, raw_opendart=_raw_opendart(financials)),
    )[0].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        security_id="000660",
        captured_at=CAPTURED,
    )
    actuals = [
        item
        for item in artifact.inputs
        if item.role in {"trailing_net_income", "book_equity", "cash_and_cash_equivalents"}
    ]
    assert all(item.authority_class is AuthorityClass.AUTHORITATIVE_SOURCE for item in actuals)


def test_alias_precedence_runs_after_source_and_pit_filters(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    financials = research.financials.copy()
    exact_mask = financials["ticker"].astype(str).eq("000660") & financials["metric"].astype(
        str
    ).str.contains("ProfitLoss#")
    owner_profit = financials.loc[exact_mask].iloc[0].copy()
    financials.loc[exact_mask, "source"] = "untrusted_vendor"
    owner_profit["metric"] = "CIS:ifrs-full_ProfitLossAttributableToOwnersOfParent"
    owner_profit["value"] = 40_000_000_000_000
    owner_profit["revision_id"] = "20260317012345"
    financials = validate_financial_statements(
        pd.concat([financials, pd.DataFrame([owner_profit])], ignore_index=True)
    )
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research",
        replace(research, financials=financials, raw_opendart=_raw_opendart(financials)),
    )[0].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        security_id="000660",
        captured_at=CAPTURED,
    )
    income = next(item for item in artifact.inputs if item.role == "trailing_net_income")
    assert income.authority_class is AuthorityClass.AUTHORITATIVE_SOURCE
    assert income.value == 40_000_000_000_000


def test_latest_fy_is_selected_before_alias_precedence(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    financials = research.financials.copy()
    latest_mask = financials["ticker"].astype(str).eq("000660") & financials["metric"].astype(
        str
    ).str.contains("ProfitLoss#")
    older_exact = financials.loc[latest_mask].iloc[0].copy()
    financials.loc[latest_mask, "metric"] = "CIS:ifrs-full_ProfitLossAttributableToOwnersOfParent"
    financials.loc[latest_mask, "value"] = 40_000_000_000_000
    older_exact["period_end"] = date(2024, 12, 31)
    older_exact["available_date"] = date(2025, 3, 17)
    older_exact["metric"] = "CIS:ifrs-full_ProfitLoss"
    older_exact["value"] = 30_000_000_000_000
    older_exact["revision_id"] = "20250317000001"
    financials = validate_financial_statements(
        pd.concat([financials, pd.DataFrame([older_exact])], ignore_index=True)
    )
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research",
        replace(research, financials=financials, raw_opendart=_raw_opendart(financials)),
    )[0].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        security_id="000660",
        captured_at=CAPTURED,
    )
    income = next(item for item in artifact.inputs if item.role == "trailing_net_income")
    assert income.value == 40_000_000_000_000
    assert income.period_end == date(2025, 12, 31)


def test_operating_profit_cannot_fallback_to_net_income(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    financials = research.financials.copy()
    net_mask = financials["ticker"].astype(str).eq("000660") & financials["metric"].astype(
        str
    ).str.contains("ProfitLoss#")
    financials.loc[net_mask, "metric"] = "CIS:ifrs-full_ProfitLossFromOperatingActivities"
    financials = validate_financial_statements(financials)
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research",
        replace(research, financials=financials, raw_opendart=_raw_opendart(financials)),
    )[0].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        security_id="000660",
        captured_at=CAPTURED,
    )
    income = next(item for item in artifact.inputs if item.role == "trailing_net_income")
    assert income.authority_class is AuthorityClass.UNSUPPORTED
    assert income.blocker == "trailing_net_income_authority_missing"


@pytest.mark.parametrize(
    "existing_fragment,compound_metric,role",
    [
        ("ProfitLoss#", "CIS:ifrs-full_ProfitLossBeforeTax", "trailing_net_income"),
        ("Equity#", "BS:ifrs-full_LiabilitiesAndEquity", "book_equity"),
    ],
)
def test_unregistered_compound_concepts_are_not_actual_aliases(
    tmp_path: Path,
    existing_fragment: str,
    compound_metric: str,
    role: str,
) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    financials = research.financials.copy()
    mask = financials["ticker"].astype(str).eq("000660") & financials["metric"].astype(
        str
    ).str.contains(existing_fragment)
    financials.loc[mask, "metric"] = compound_metric
    financials = validate_financial_statements(financials)
    research_dir = write_fundamental_macro_snapshot(
        tmp_path / "research",
        replace(research, financials=financials, raw_opendart=_raw_opendart(financials)),
    )[0].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        security_id="000660",
        captured_at=CAPTURED,
    )
    actual = next(item for item in artifact.inputs if item.role == role)
    assert actual.authority_class is AuthorityClass.UNSUPPORTED
    assert actual.blocker == f"{role}_authority_missing"


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
    assert _replay(directory, market, research, legacy) == artifact
    assert (
        revalidate_persisted_valuation_authority(
            directory,
            market_directory=market,
            research_directory=research,
            legacy_valuation_directory=legacy,
        )
        == artifact
    )


def test_modified_share_source_is_rejected_by_canonical_replay(tmp_path: Path) -> None:
    _, market, research, legacy = _artifact(tmp_path)
    (legacy / "shares.csv").write_text("ticker,issued_shares\n000660,1\n", encoding="utf-8")
    with pytest.raises(ValuationAuthorityError, match="canonical identity"):
        build_valuation_authority(
            market_directory=market,
            research_directory=research,
            legacy_valuation_directory=legacy,
            security_id="000660",
            captured_at=CAPTURED,
        )


def test_forged_authority_json_fails_digest_before_it_can_self_authorize(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    directory = _persist(artifact, tmp_path / "authority", market, research, legacy)
    _rewrite(
        directory / "authority.json",
        lambda value: value.__setitem__("share_count_authority_established", True),
    )
    with pytest.raises(ValuationAuthorityError, match="digest"):
        _replay(directory, market, research, legacy)


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


def test_self_consistent_forged_persisted_authority_fails_upstream_replay(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    forged = replace(
        artifact,
        inputs=tuple(
            replace(item, value=1.0) if item.role == "current_price" else item
            for item in artifact.inputs
        ),
    )
    payload_bytes = (
        json.dumps(forged.payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    directory = tmp_path / (
        f"{forged.captured_at.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        f"__{forged.artifact_id[:12]}"
    )
    directory.mkdir()
    (directory / "authority.json").write_bytes(payload_bytes)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_id": forged.artifact_id,
                "captured_at": forged.captured_at.isoformat(),
                "evaluation_date": forged.evaluation_date.isoformat(),
                "security_id": forged.security_id,
                "files": {"authority.json": hashlib.sha256(payload_bytes).hexdigest()},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValuationAuthorityError, match="differs from upstream replay"):
        _replay(directory, market, research, legacy)


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
        _replay(directory, market, research, legacy)


def test_manifest_duplicate_identity_tamper_is_rejected(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    directory = _persist(artifact, tmp_path / "authority", market, research, legacy)
    _rewrite(
        directory / "manifest.json",
        lambda value: value.__setitem__("security_id", "005930"),
    )
    with pytest.raises(ValuationAuthorityError, match="manifest identity"):
        _replay(directory, market, research, legacy)


def test_empty_legacy_file_claim_cannot_receive_class_b(tmp_path: Path) -> None:
    market, research, legacy = _sources(tmp_path)
    _rewrite(legacy / "manifest.json", lambda value: value.__setitem__("files", []))
    with pytest.raises(ValuationAuthorityError, match="file set"):
        build_valuation_authority(
            market_directory=market,
            research_directory=research,
            legacy_valuation_directory=legacy,
            security_id="000660",
            captured_at=CAPTURED,
        )


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


def test_legacy_capture_after_authority_is_rejected(tmp_path: Path) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    research = _research(market.snapshot_id)
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research)[0].parent
    shares = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "security_class": "common",
                "issued_shares": 100,
                "treasury_shares": 0,
            }
        ]
    )
    legacy_snapshot = ValuationEvidenceSnapshot(
        captured_at=CAPTURED + timedelta(seconds=1),
        evaluation_date=research.evaluation_date,
        research_snapshot_id=research.snapshot_id,
        market_snapshot_id=market.snapshot_id,
        history_years=3,
        shares=shares,
        security_values=pd.DataFrame({"ticker": ["000660"]}),
        financial_history=pd.DataFrame({"ticker": ["000660"]}),
        valuation_metrics=pd.DataFrame(
            {
                "ticker": ["000660"],
                "market_cap_complete": [False],
                "valuation_score": [None],
            }
        ),
        raw_valuation={
            "source_research_snapshot_id": research.snapshot_id,
            "source_market_snapshot_id": market.snapshot_id,
        },
    )
    legacy = write_valuation_evidence_snapshot(tmp_path / "legacy", legacy_snapshot)[0].parent
    with pytest.raises(ValuationAuthorityError, match="capture follows"):
        build_valuation_authority(
            market_directory=market_dir,
            research_directory=research_dir,
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
    trailing = next(item for item in artifact.methods if item.method is ValuationMethod.TRAILING_PE)
    assert "trailing_net_income_authority_missing" in trailing.blockers
    assert "trailing_net_income_authority_missing" in artifact.payload_without_id()["blockers"]


@pytest.mark.parametrize(
    "policy,expected",
    [
        (RevisionPolicy.FIRST_RELEASE, 42_947_902_000_000),
        (RevisionPolicy.LATEST_KNOWN, 43_000_000_000_000),
    ],
)
def test_financial_revision_policy_selects_one_known_revision(
    tmp_path: Path, policy: RevisionPolicy, expected: int
) -> None:
    market = _market()
    market_dir = write_market_intelligence_snapshot(tmp_path / "market", market)[0].parent
    original = _research(market.snapshot_id)
    base = (
        original.financials.loc[
            original.financials["ticker"].astype(str).eq("000660")
            & original.financials["metric"].astype(str).str.startswith("CIS:ifrs-full_ProfitLoss#")
        ]
        .iloc[0]
        .copy()
    )
    base["value"] = 43_000_000_000_000
    base["revision_id"] = "20260401000001"
    base["revision_sequence"] = 1
    base["available_date"] = date(2026, 4, 1)
    revised = validate_financial_statements(
        pd.concat([original.financials, pd.DataFrame([base])], ignore_index=True)
    )
    research_snapshot = replace(
        original,
        revision_policy=policy,
        financials=revised,
        raw_opendart=_raw_opendart(revised),
    )
    research_dir = write_fundamental_macro_snapshot(tmp_path / "research", research_snapshot)[
        0
    ].parent
    artifact = build_valuation_authority(
        market_directory=market_dir,
        research_directory=research_dir,
        legacy_valuation_directory=None,
        security_id="000660",
        captured_at=CAPTURED,
    )
    income = next(item for item in artifact.inputs if item.role == "trailing_net_income")
    assert income.value == expected


def test_price_mutation_is_detected_by_upstream_replay(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    directory = _persist(artifact, tmp_path / "authority", market, research, legacy)
    _rewrite(
        directory / "authority.json", lambda value: value["inputs"][3].__setitem__("value", 1.0)
    )
    with pytest.raises(ValuationAuthorityError):
        _replay(directory, market, research, legacy)
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
    with pytest.raises(ValuationAuthorityError, match="junction or alias"):
        _persist(artifact, link, market, research, legacy)


def test_output_repository_symlink_ancestor_escape_is_rejected(tmp_path: Path) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValuationAuthorityError, match="junction or alias"):
        _persist(artifact, alias / "authority", market, research, legacy)
    assert not (outside / "authority").exists()


def test_publication_fsyncs_staged_and_repository_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact, market, research, legacy = _artifact(tmp_path)
    synced: list[Path] = []
    monkeypatch.setattr(
        valuation_authority_module,
        "_fsync_directory",
        lambda path: synced.append(Path(path)),
    )
    repository = tmp_path / "authority"
    _persist(artifact, repository, market, research, legacy)
    assert len(synced) == 2
    assert synced[0].name.startswith(".")
    assert synced[1] == repository.resolve()


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


def test_cli_validates_full_batch_before_publication(tmp_path: Path, capsys) -> None:
    market, research, legacy = _sources(tmp_path)
    output = tmp_path / "acceptance"
    result = authority_cli_main(
        [
            "--market-snapshot",
            str(market),
            "--research-snapshot",
            str(research),
            "--legacy-valuation-snapshot",
            str(legacy),
            "--security",
            "000660",
            "--security",
            "999999",
            "--captured-at",
            CAPTURED.isoformat(),
            "--output",
            str(output),
        ]
    )
    assert result == 2
    assert not output.exists()
    assert "exactly one trusted market price" in capsys.readouterr().err
