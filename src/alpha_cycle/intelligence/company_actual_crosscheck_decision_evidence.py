"""Independent OpenDART-versus-SEC company-actual crosscheck for SK hynix."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date

from alpha_cycle.intelligence.opendart_provisional_earnings_decision_evidence import (
    ProvisionalEarningsDecisionEvidence,
)
from alpha_cycle.intelligence.sec_company_actual import SecCompanyActualEvidence


@dataclass(frozen=True)
class CompanyActualCrosscheckEvidence:
    evidence_id: str
    ticker: str
    period_end: date
    opendart_evidence_id: str
    sec_evidence_id: str
    revenue_delta_krw_million: float
    operating_income_delta_krw_million: float
    net_income_delta_krw_million: float
    absolute_tolerance_krw_million: float
    crosscheck_certified: bool
    company_level_actual_only: bool = True
    product_baseline_eligible: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64:
            raise ValueError("Company actual crosscheck evidence_id must be SHA-256")
        if self.ticker != "000660":
            raise ValueError("Company actual crosscheck v1 supports SK hynix only")
        if self.absolute_tolerance_krw_million < 0:
            raise ValueError("Company actual crosscheck tolerance cannot be negative")
        if not self.company_level_actual_only:
            raise ValueError("Company actual crosscheck must remain company-level only")
        if self.product_baseline_eligible or self.numeric_forecast_enabled or self.decision_score_enabled:
            raise ValueError("Company actual crosscheck cannot widen product/model/score gates")


def build_company_actual_crosscheck(
    opendart: ProvisionalEarningsDecisionEvidence,
    sec: SecCompanyActualEvidence,
    *,
    absolute_tolerance_krw_million: float = 0.5,
) -> CompanyActualCrosscheckEvidence:
    if opendart.ticker != sec.ticker or opendart.ticker != "000660":
        raise ValueError("Company actual crosscheck issuer identity mismatch")
    if opendart.period_start != sec.period_start or opendart.period_end != sec.period_end:
        raise ValueError("Company actual crosscheck accounting period mismatch")
    if absolute_tolerance_krw_million < 0:
        raise ValueError("Company actual crosscheck tolerance cannot be negative")

    revenue_delta = sec.metrics.revenue - opendart.metrics.revenue
    operating_income_delta = sec.metrics.operating_income - opendart.metrics.operating_income
    net_income_delta = sec.metrics.net_income - opendart.metrics.net_income
    certified = all(
        abs(value) <= absolute_tolerance_krw_million
        for value in (revenue_delta, operating_income_delta, net_income_delta)
    )
    payload = {
        "ticker": opendart.ticker,
        "period_end": opendart.period_end.isoformat(),
        "opendart_evidence_id": opendart.evidence_id,
        "sec_evidence_id": sec.evidence_id,
        "revenue_delta_krw_million": revenue_delta,
        "operating_income_delta_krw_million": operating_income_delta,
        "net_income_delta_krw_million": net_income_delta,
        "absolute_tolerance_krw_million": absolute_tolerance_krw_million,
        "crosscheck_certified": certified,
        "company_level_actual_only": True,
        "product_baseline_eligible": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    evidence_id = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return CompanyActualCrosscheckEvidence(
        evidence_id=evidence_id,
        ticker=opendart.ticker,
        period_end=opendart.period_end,
        opendart_evidence_id=opendart.evidence_id,
        sec_evidence_id=sec.evidence_id,
        revenue_delta_krw_million=revenue_delta,
        operating_income_delta_krw_million=operating_income_delta,
        net_income_delta_krw_million=net_income_delta,
        absolute_tolerance_krw_million=absolute_tolerance_krw_million,
        crosscheck_certified=certified,
    )


def append_company_actual_crosscheck_report(
    report: str,
    evidence: CompanyActualCrosscheckEvidence,
) -> str:
    status = "certified" if evidence.crosscheck_certified else "mismatch"
    lines = [
        report.rstrip(),
        "",
        "## Company Actual Dual-Official Cross-check (OpenDART ↔ SEC)",
        "",
        f"- status: `{status}` / evidence `{evidence.evidence_id[:12]}`",
        (
            "- 두 공식 채널의 회사 전체 2Q 잠정실적만 비교합니다. 일치해도 제품별 "
            "baseline, forecast, Expectation Gap, decision score를 자동으로 열지 않습니다."
        ),
        "",
        "| metric delta (SEC - OpenDART) | KRW mn |",
        "|---|---:|",
        f"| revenue | {evidence.revenue_delta_krw_million:.3f} |",
        f"| operating income | {evidence.operating_income_delta_krw_million:.3f} |",
        f"| net income | {evidence.net_income_delta_krw_million:.3f} |",
        f"| tolerance | ±{evidence.absolute_tolerance_krw_million:.3f} |",
        "",
        "- product baseline eligible: `false`; numeric forecast: `false`; score: `false`",
    ]
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "CompanyActualCrosscheckEvidence",
    "append_company_actual_crosscheck_report",
    "build_company_actual_crosscheck",
]
