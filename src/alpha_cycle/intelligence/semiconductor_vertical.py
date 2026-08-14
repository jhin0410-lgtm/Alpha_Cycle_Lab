"""Semiconductor vertical research coverage from currently connected live evidence.

This module answers a different question from the existing semiconductor cycle
heuristic: not "is the cycle expanding?", but "do we have the evidence required
to carry a semiconductor thesis all the way from demand/supply through company
earnings, expectations, valuation, catalysts, and market confirmation?"

The output is deliberately non-scoring.  Missing memory-price/HBM/consensus data
stays missing instead of being replaced by a convenient proxy.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import cast

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.sector_vertical import (
    SectorRequirementState,
    SectorVerticalCoverage,
    evaluate_sector_vertical_coverage,
)
from alpha_cycle.intelligence.sector_vertical_registry import SEMICONDUCTOR

SEMICONDUCTOR_TICKERS = ("005930", "000660")


def _number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT or isinstance(value, bool):
        return None
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted):
        return None
    result = float(converted)
    return result if math.isfinite(result) else None


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes"}


def _state(
    key: str,
    status: str,
    summary: str,
    *,
    source: str | None = None,
    blocker: str | None = None,
) -> SectorRequirementState:
    return SectorRequirementState(
        requirement_key=key,
        status=status,
        evidence_summary=summary,
        source_scope=source,
        blocker=blocker,
    )


def _scorecard_lookup(scorecards: pd.DataFrame) -> dict[str, Mapping[str, object]]:
    if "ticker" not in scorecards.columns:
        raise ValueError("Semiconductor vertical scorecards must contain ticker")
    result: dict[str, Mapping[str, object]] = {}
    for raw_value in scorecards.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
        ticker = str(raw.get("ticker", "")).strip().zfill(6)
        if ticker in result:
            raise ValueError(f"Semiconductor vertical duplicate scorecard ticker: {ticker}")
        result[ticker] = raw
    return result


def _latest_quarter_lookup(
    financial_history: pd.DataFrame,
) -> dict[str, Mapping[str, object]]:
    required = {"ticker", "period_label", "period_end", "available_date"}
    if financial_history.empty or not required.issubset(financial_history.columns):
        return {}
    history = financial_history.copy()
    history["ticker"] = history["ticker"].astype("string").str.zfill(6)
    history = history.loc[
        history["ticker"].isin(SEMICONDUCTOR_TICKERS)
        & history["period_label"].astype(str).isin({"Q1", "Q2", "Q3", "Q4"})
    ].copy()
    if history.empty:
        return {}
    history["period_end"] = pd.to_datetime(history["period_end"], errors="raise")
    history["available_date"] = pd.to_datetime(history["available_date"], errors="raise")
    result: dict[str, Mapping[str, object]] = {}
    for ticker, group in history.groupby("ticker", sort=False):
        ordered = group.sort_values(
            ["period_end", "available_date"],
            kind="stable",
        )
        result[str(ticker)] = cast(
            Mapping[str, object],
            {str(key): value for key, value in ordered.iloc[-1].to_dict().items()},
        )
    return result


def _catalyst_counts(catalysts: pd.DataFrame) -> dict[str, int]:
    if catalysts.empty or "ticker" not in catalysts.columns:
        return {}
    values = catalysts.copy()
    values["ticker"] = values["ticker"].astype("string").str.zfill(6)
    return {
        str(ticker): int(len(group))
        for ticker, group in values.groupby("ticker", sort=False)
    }


def _industry_metric(row: Mapping[str, object], key: str) -> float | None:
    return _number(row.get(f"industry_{key}"))


def _industry_available(row: Mapping[str, object]) -> bool:
    return _bool(row.get("industry_evidence_available"))


def _financial_summary(row: Mapping[str, object]) -> tuple[bool, str]:
    revenue_yoy = _number(row.get("revenue_yoy"))
    operating_yoy = _number(row.get("operating_income_yoy"))
    margin_change = _number(row.get("operating_margin_change_yoy_pp"))
    available = all(value is not None for value in (revenue_yoy, operating_yoy, margin_change))
    if not available:
        return False, "최근 분기 매출/영업이익/마진 YoY 연결이 불완전합니다."
    return (
        True,
        "최근 분기 매출 YoY "
        f"{revenue_yoy * 100:+.1f}%, 영업이익 YoY {operating_yoy * 100:+.1f}%, "
        f"마진 YoY 변화 {margin_change:+.1f}%p.",
    )


def _capex_summary(row: Mapping[str, object]) -> tuple[bool, str]:
    capex = _number(row.get("capex_ytd"))
    prior = _number(row.get("capex_prior_ytd"))
    derived = _bool(row.get("derived"))
    if capex is None or prior is None or derived:
        return False, "최근 non-derived 분기 issuer CAPEX 비교가 불완전합니다."
    if prior == 0:
        return True, "issuer CAPEX YTD는 연결됐지만 전년 비교 기준이 0이라 growth는 계산하지 않습니다."
    growth = abs(capex) / abs(prior) - 1.0
    return True, f"issuer CAPEX YTD YoY proxy {growth * 100:+.1f}%가 연결됐습니다."


def _market_summary(row: Mapping[str, object]) -> tuple[bool, str]:
    return_20 = _number(row.get("return_20"))
    return_60 = _number(row.get("return_60"))
    confirmed = row.get("cycle_proxy_market_confirmed")
    if return_20 is None and return_60 is None and confirmed is None:
        return False, "가격 추세 확인 데이터가 없습니다."
    parts: list[str] = []
    if return_20 is not None:
        parts.append(f"20일 {return_20 * 100:+.1f}%")
    if return_60 is not None:
        parts.append(f"60일 {return_60 * 100:+.1f}%")
    if isinstance(confirmed, bool):
        parts.append("cycle proxy 시장확인=" + ("yes" if confirmed else "no"))
    return True, ", ".join(parts) + "."


def _valuation_summary(row: Mapping[str, object]) -> tuple[str, str]:
    pb_usable = _bool(row.get("historical_pb_evidence_available"))
    latest_pb = _number(row.get("historical_pb_latest_pb"))
    pb_percentile = _number(row.get("historical_pb_latest_pb_percentile"))
    ttm_roe = _number(row.get("pb_roe_regime_ttm_roe"))
    roe_ready = _bool(row.get("pb_roe_regime_ttm_roe_history_ready"))
    if not pb_usable or latest_pb is None:
        return "missing", "현재 사용 가능한 own-history P/B 증거가 없습니다."
    parts = [f"own-history P/B {latest_pb:.2f}x"]
    if pb_percentile is not None:
        parts.append(f"P/B percentile {pb_percentile:.1f}%")
    if ttm_roe is not None:
        parts.append(f"TTM ROE proxy {ttm_roe * 100:.1f}%")
    if roe_ready:
        return "partial", ", ".join(parts) + "; forward ROE/cost of equity는 미연결입니다."
    return "partial", ", ".join(parts) + "; ROE history/forward ROE/cost of equity가 아직 충분하지 않습니다."


def _build_states(
    ticker: str,
    scorecard: Mapping[str, object],
    financial: Mapping[str, object] | None,
    catalyst_count: int,
    macro_available: bool,
) -> dict[str, SectorRequirementState]:
    states: dict[str, SectorRequirementState] = {}

    states["macro_liquidity"] = _state(
        "macro_liquidity",
        "partial" if macro_available else "missing",
        (
            "국내 금리·원달러 등 macro base는 연결됐지만 미국 실질금리/DXY/글로벌 "
            "유동성·SOX 자금흐름은 아직 vertical 입력으로 연결되지 않았습니다."
            if macro_available
            else "반도체 vertical에 연결 가능한 macro evidence가 없습니다."
        ),
        source="BOK_ECOS_and_decision_macro" if macro_available else None,
        blocker=None if macro_available else "macro_vertical_not_connected",
    )

    shipment_yoy = _industry_metric(scorecard, "shipment_yoy_pct")
    shipment_mom = _industry_metric(scorecard, "shipment_mom_sa_pct")
    if _industry_available(scorecard) and (shipment_yoy is not None or shipment_mom is not None):
        states["end_demand"] = _state(
            "end_demand",
            "partial",
            "KOSIS 반도체 출하 aggregate는 연결됐지만 server/AI/PC/mobile end-demand 분해는 없습니다.",
            source="kosis_semiconductor_industry_evidence",
        )
    else:
        states["end_demand"] = _state(
            "end_demand",
            "missing",
            "최종수요를 설명할 산업 출하/수요 증거가 없습니다.",
            blocker="end_demand_source_not_connected",
        )

    states["memory_pricing"] = _state(
        "memory_pricing",
        "missing",
        "DRAM/NAND 계약·현물 가격을 현재 공식/라이선스된 소스로 연결하지 않았습니다.",
        blocker="certified_memory_price_source_missing",
    )
    states["hbm_demand_mix"] = _state(
        "hbm_demand_mix",
        "missing",
        "HBM bit demand·세대별 mix·ASP를 source-bounded evidence로 연결하지 않았습니다.",
        blocker="hbm_demand_mix_source_missing",
    )

    inventory_yoy = _industry_metric(scorecard, "inventory_yoy_pct")
    inventory_mom = _industry_metric(scorecard, "inventory_mom_sa_pct")
    if _industry_available(scorecard) and inventory_yoy is not None:
        states["inventory_cycle"] = _state(
            "inventory_cycle",
            "available",
            f"KOSIS 재고 YoY {inventory_yoy:+.2f}%"
            + (f", SA MoM {inventory_mom:+.2f}%." if inventory_mom is not None else "."),
            source="kosis_semiconductor_industry_evidence",
        )
    else:
        states["inventory_cycle"] = _state(
            "inventory_cycle",
            "missing",
            "산업 재고 cycle 증거가 없습니다.",
            blocker="industry_inventory_evidence_missing",
        )

    capacity_yoy = _industry_metric(scorecard, "capacity_yoy_pct")
    utilization_yoy = _industry_metric(scorecard, "utilization_yoy_pct")
    utilization_mom = _industry_metric(scorecard, "utilization_mom_sa_pct")
    if _industry_available(scorecard) and capacity_yoy is not None and utilization_yoy is not None:
        states["capacity_utilization"] = _state(
            "capacity_utilization",
            "available",
            f"KOSIS 생산능력 YoY {capacity_yoy:+.2f}%, 가동률 YoY {utilization_yoy:+.2f}%"
            + (f", SA MoM {utilization_mom:+.2f}%." if utilization_mom is not None else "."),
            source="kosis_semiconductor_industry_evidence",
        )
    else:
        states["capacity_utilization"] = _state(
            "capacity_utilization",
            "missing",
            "생산능력·가동률 증거가 불완전합니다.",
            blocker="capacity_utilization_evidence_missing",
        )

    capex_ok, capex_text = _capex_summary(financial or {})
    if capex_ok and capacity_yoy is not None:
        states["supplier_capex"] = _state(
            "supplier_capex",
            "partial",
            capex_text + " KOSIS capacity도 연결됐지만 글로벌 supplier/wafer CAPEX는 없습니다.",
            source="OpenDART_plus_KOSIS",
        )
    else:
        states["supplier_capex"] = _state(
            "supplier_capex",
            "missing",
            capex_text,
            blocker="supplier_capex_evidence_incomplete",
        )

    states["hbm_capacity_yield"] = _state(
        "hbm_capacity_yield",
        "missing",
        "HBM wafer allocation·TSV/advanced packaging capacity·yield·qualification 병목을 연결하지 않았습니다.",
        blocker="hbm_capacity_yield_source_missing",
    )
    states["competitive_position"] = _state(
        "competitive_position",
        "missing",
        "HBM 세대별 qualification·점유율·technology node 경쟁력을 structured evidence로 연결하지 않았습니다.",
        blocker="company_competitive_evidence_missing",
    )
    states["business_mix_drag"] = _state(
        "business_mix_drag",
        "partial",
        (
            "OpenDART 연결 재무는 있으나 HBM/DRAM/NAND/foundry/mobile 등 segment-level "
            f"mix transmission은 아직 구조화되지 않았습니다 ({ticker})."
        ),
        source="OpenDART_financials",
    )

    financial_ok, financial_text = _financial_summary(financial or {})
    states["earnings_transmission"] = _state(
        "earnings_transmission",
        "available" if financial_ok else "missing",
        financial_text,
        source="OpenDART_financial_history" if financial_ok else None,
        blocker=None if financial_ok else "quarterly_earnings_transmission_missing",
    )

    kis_available = _bool(scorecard.get("kis_forward_evidence_available"))
    change_verified = _bool(scorecard.get("kis_estimate_snapshot_change_verified"))
    if kis_available:
        detail = (
            "KIS raw forward structure/change snapshot은 존재하지만 provider semantics·consensus·revision 인증이 없어 차단합니다."
        )
        if change_verified:
            detail = "KIS snapshot change는 관측됐지만 consensus/revision semantics가 인증되지 않아 투자 revision으로 사용하지 않습니다."
        states["expectation_revision"] = _state(
            "expectation_revision",
            "blocked",
            detail,
            source="kis_estimate_perform_raw_unclassified",
            blocker="consensus_and_revision_semantics_not_certified",
        )
    else:
        states["expectation_revision"] = _state(
            "expectation_revision",
            "missing",
            "인증 가능한 forward consensus/revision source가 연결되지 않았습니다.",
            blocker="certified_consensus_source_missing",
        )

    if catalyst_count > 0:
        states["catalyst_calendar"] = _state(
            "catalyst_calendar",
            "partial",
            f"OpenDART 기반 catalyst 후보 {catalyst_count}건은 있으나 1/3/6/12개월 event taxonomy와 surprise expectation은 미완성입니다.",
            source="OpenDART_disclosures",
        )
    else:
        states["catalyst_calendar"] = _state(
            "catalyst_calendar",
            "missing",
            "현재 종목에 연결된 catalyst 후보가 없습니다.",
            blocker="catalyst_calendar_not_connected",
        )

    valuation_status, valuation_text = _valuation_summary(scorecard)
    states["valuation_regime"] = _state(
        "valuation_regime",
        valuation_status,
        valuation_text,
        source="historical_PB_and_OpenDART_equity" if valuation_status != "missing" else None,
        blocker=None if valuation_status != "missing" else "valuation_regime_evidence_missing",
    )

    market_ok, market_text = _market_summary(scorecard)
    flow_verified = _bool(scorecard.get("investor_flow_evidence_verified"))
    flow_available = _bool(scorecard.get("investor_flow_available")) or scorecard.get(
        "investor_flow_snapshot_id"
    ) is not None
    if market_ok and flow_verified:
        market_status = "available"
        market_text += " same-session investor-flow evidence도 검증됐습니다."
    elif market_ok or flow_available:
        market_status = "partial"
        market_text += " 현재 same-session investor flow는 검증되지 않아 가격 확인과 분리합니다."
    else:
        market_status = "missing"
    states["flow_price_confirmation"] = _state(
        "flow_price_confirmation",
        market_status,
        market_text,
        source="Kiwoom_market_and_investor_flow" if market_status != "missing" else None,
        blocker=None if market_status != "missing" else "market_flow_confirmation_missing",
    )

    states["export_control_geopolitics"] = _state(
        "export_control_geopolitics",
        "missing",
        "미국/중국 수출규제·AI accelerator control·장비 규제를 structured primary-source evidence로 연결하지 않았습니다.",
        blocker="semiconductor_policy_primary_sources_missing",
    )
    return states


@dataclass(frozen=True)
class SemiconductorVerticalAssessment:
    """Non-scoring semiconductor end-to-end research coverage assessment."""

    assessment_id: str
    evaluation_date: date
    coverages: tuple[SectorVerticalCoverage, ...]
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.assessment_id) != 64 or any(
            character not in "0123456789abcdef" for character in self.assessment_id
        ):
            raise ValueError("Semiconductor vertical assessment_id must be SHA-256")
        if not self.coverages:
            raise ValueError("Semiconductor vertical assessment requires company coverage")
        if self.decision_score_enabled:
            raise ValueError("Semiconductor vertical assessment must remain non-scoring")

    def as_dict(self) -> dict[str, object]:
        return {
            "assessment_id": self.assessment_id,
            "evaluation_date": self.evaluation_date.isoformat(),
            "sector_id": SEMICONDUCTOR.sector_id,
            "coverages": [coverage.as_dict() for coverage in self.coverages],
            "decision_score_enabled": False,
        }


def build_semiconductor_vertical_assessment(
    scorecards: pd.DataFrame,
    financial_history: pd.DataFrame,
    catalysts: pd.DataFrame,
    macro_regime: pd.DataFrame,
    *,
    evaluation_date: date,
) -> SemiconductorVerticalAssessment:
    """Build company-specific semiconductor research coverage from live evidence."""

    score_lookup = _scorecard_lookup(scorecards)
    financial_lookup = _latest_quarter_lookup(financial_history)
    catalyst_lookup = _catalyst_counts(catalysts)
    macro_available = not macro_regime.empty
    coverages: list[SectorVerticalCoverage] = []

    for ticker in SEMICONDUCTOR_TICKERS:
        scorecard = score_lookup.get(ticker)
        if scorecard is None:
            continue
        states = _build_states(
            ticker,
            scorecard,
            financial_lookup.get(ticker),
            catalyst_lookup.get(ticker, 0),
            macro_available,
        )
        coverages.append(
            evaluate_sector_vertical_coverage(SEMICONDUCTOR, ticker, states)
        )
    if not coverages:
        raise ValueError("Semiconductor vertical found no supported semiconductor tickers")

    payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "sector_id": SEMICONDUCTOR.sector_id,
        "coverages": [coverage.as_dict() for coverage in coverages],
        "decision_score_enabled": False,
    }
    assessment_id = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return SemiconductorVerticalAssessment(
        assessment_id=assessment_id,
        evaluation_date=evaluation_date,
        coverages=tuple(coverages),
        decision_score_enabled=False,
    )


def attach_semiconductor_vertical_to_scorecards(
    scorecards: pd.DataFrame,
    assessment: SemiconductorVerticalAssessment,
) -> pd.DataFrame:
    """Attach research-readiness metadata without touching decision scores."""

    if "ticker" not in scorecards.columns:
        raise ValueError("Scorecards must contain ticker")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    rows: list[dict[str, object]] = []
    for coverage in assessment.coverages:
        rows.append(
            {
                "ticker": coverage.ticker,
                "sector_vertical_id": coverage.sector_id,
                "sector_vertical_assessment_id": assessment.assessment_id,
                "sector_vertical_readiness_status": coverage.readiness_status,
                "sector_vertical_required_available": coverage.required_available,
                "sector_vertical_required_total": coverage.required_total,
                "sector_vertical_important_available": coverage.important_available,
                "sector_vertical_important_total": coverage.important_total,
                "sector_vertical_missing_required_json": json.dumps(
                    list(coverage.missing_required), ensure_ascii=False
                ),
                "sector_vertical_partial_required_json": json.dumps(
                    list(coverage.partial_required), ensure_ascii=False
                ),
                "sector_vertical_blocked_required_json": json.dumps(
                    list(coverage.blocked_required), ensure_ascii=False
                ),
                "sector_vertical_missing_important_json": json.dumps(
                    list(coverage.missing_important), ensure_ascii=False
                ),
                "sector_vertical_evidence_json": json.dumps(
                    coverage.as_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "sector_vertical_decision_score_enabled": False,
            }
        )
    supplement = pd.DataFrame(rows)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def sync_record_semiconductor_vertical_fields(
    records: pd.DataFrame,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    fields = [
        "ticker",
        "sector_vertical_id",
        "sector_vertical_assessment_id",
        "sector_vertical_readiness_status",
        "sector_vertical_required_available",
        "sector_vertical_required_total",
        "sector_vertical_important_available",
        "sector_vertical_important_total",
        "sector_vertical_missing_required_json",
        "sector_vertical_partial_required_json",
        "sector_vertical_blocked_required_json",
        "sector_vertical_missing_important_json",
        "sector_vertical_decision_score_enabled",
    ]
    available = [column for column in fields if column in scorecards.columns]
    supplement = scorecards.loc[:, available].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [
        column for column in available if column != "ticker" and column in result.columns
    ]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _status_text(status: str) -> str:
    return {
        "available": "연결",
        "partial": "부분",
        "blocked": "차단",
        "missing": "미연결",
    }[status]


def append_semiconductor_vertical_report(
    report: str,
    assessment: SemiconductorVerticalAssessment,
) -> str:
    """Append an explicit research-completeness map to the live decision report."""

    lines = [
        report.rstrip(),
        "",
        "## Semiconductor Vertical v1 연구 커버리지 (비점수)",
        "",
        f"- assessment: `{assessment.assessment_id[:12]}` / evaluation `{assessment.evaluation_date.isoformat()}`",
        f"- 핵심 질문: {SEMICONDUCTOR.thesis_question}",
        "- 아래 표는 투자점수가 아니라 end-to-end thesis를 만들기 위해 어떤 증거가 아직 필요한지 보여줍니다.",
        "- `partial`·`blocked`·`missing`은 0점으로 환산하지 않으며, 없는 데이터를 proxy로 임의 대체하지 않습니다.",
        "",
        "| 종목 | 상태 | 필수 연결 | 중요 연결 | 필수 미연결 | 필수 부분 | 필수 차단 |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for coverage in assessment.coverages:
        lines.append(
            f"| {coverage.ticker} | {coverage.readiness_status} | "
            f"{coverage.required_available}/{coverage.required_total} | "
            f"{coverage.important_available}/{coverage.important_total} | "
            f"{', '.join(coverage.missing_required) or '-'} | "
            f"{', '.join(coverage.partial_required) or '-'} | "
            f"{', '.join(coverage.blocked_required) or '-'} |"
        )

    for coverage in assessment.coverages:
        lines.extend(
            [
                "",
                f"### {coverage.ticker} vertical evidence map",
                "",
                "| 영역 | 질문 | 우선순위 | 상태 | 현재 근거 / 다음 공백 |",
                "|---|---|---|---|---|",
            ]
        )
        for state in coverage.states:
            requirement = SEMICONDUCTOR.requirement(state.requirement_key)
            detail = state.evidence_summary
            if state.blocker:
                detail += f" blocker=`{state.blocker}`"
            lines.append(
                f"| {requirement.domain} | {requirement.label} | {requirement.priority} | "
                f"{_status_text(state.status)} | {detail} |"
            )
        priority_keys = list(coverage.missing_required) + list(coverage.blocked_required) + list(
            coverage.partial_required
        )
        if priority_keys:
            lines.extend(["", "- 다음 데이터 연결 우선순위:"])
            for key in priority_keys:
                requirement = SEMICONDUCTOR.requirement(key)
                sources = ", ".join(requirement.preferred_sources) or "source research required"
                lines.append(f"  - `{key}`: {requirement.label} → {sources}")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "SEMICONDUCTOR_TICKERS",
    "SemiconductorVerticalAssessment",
    "append_semiconductor_vertical_report",
    "attach_semiconductor_vertical_to_scorecards",
    "build_semiconductor_vertical_assessment",
    "sync_record_semiconductor_vertical_fields",
]
