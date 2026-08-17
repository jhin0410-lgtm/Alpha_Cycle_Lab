"""Certify pre-2023 SK hynix direct product revenue by exact consolidated tie-out.

The preserved filings expose two plausible DRAM/NAND tables for each historical period:
one from consolidated financial statements and one from separate financial statements.
This layer selects neither by table order nor by fuzzy labels. A candidate is certifiable
only when its direct-quarter total exactly reconciles to the independently verified
consolidated company revenue for the same filing revision.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_source_closure import (
    ProductRevenueSourceClosurePeriod,
    ProductRevenueTableWitness,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_source_layer_resolution import (
    VerifiedCompanyProfitabilityConstraint,
)

_EXPECTED_PERIODS = (
    "2021Q1",
    "2021Q2",
    "2021Q3",
    "2022Q1",
    "2022Q2",
    "2022Q3",
)
_DRAM_LABELS = frozenset({"dram", "d ram", "d램", "디램"})
_NAND_LABELS = frozenset({"nand", "nand flash", "낸드", "낸드플래시"})
_OTHER_LABELS = frozenset({"기타", "other", "others"})
_TOTAL_LABELS = frozenset({"합계", "합 계", "total"})
_CURRENT_HEADERS = frozenset({"당분기", "당반기"})


def _norm(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split()).casefold()


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _integral_million_krw(value: str, label: str) -> int:
    text = value.strip().replace(",", "")
    if not text or text == "-":
        raise ValueError(f"Product revenue {label} is missing")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Product revenue {label} is not numeric: {value}") from exc
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"Product revenue {label} must be integral million KRW")
    parsed = int(amount)
    if parsed < 0:
        raise ValueError(f"Product revenue {label} cannot be negative")
    return parsed


def _row_for_label(
    witness: ProductRevenueTableWitness,
    labels: frozenset[str],
    label: str,
) -> tuple[str, ...]:
    rows = [row for row in witness.rows if row and _norm(row[0]) in labels]
    if len(rows) != 1:
        raise ValueError(f"Product revenue {label} row must resolve uniquely: count={len(rows)}")
    return rows[0]


def _direct_quarter_column(witness: ProductRevenueTableWitness) -> tuple[int, str]:
    three_month_columns = [
        column
        for row in witness.rows[:4]
        for column, value in enumerate(row)
        if column > 0 and _norm(value) == "3개월"
    ]
    if three_month_columns:
        return min(three_month_columns), "direct_quarter_3_month"

    current_columns = [
        column
        for row in witness.rows[:3]
        for column, value in enumerate(row)
        if column > 0 and _norm(value) in _CURRENT_HEADERS
    ]
    unique = sorted(set(current_columns))
    if len(unique) != 1:
        raise ValueError(
            "Product revenue direct-quarter column must resolve uniquely when 3-month "
            f"header is absent: columns={unique}"
        )
    return unique[0], "direct_quarter_current_period"


def _amount_at(row: tuple[str, ...], column: int, label: str) -> int:
    if column >= len(row):
        raise ValueError(f"Product revenue {label} row lacks selected quarter column")
    return _integral_million_krw(row[column], label)


@dataclass(frozen=True)
class ProductRevenueCandidateReview:
    member_name: str
    table_index: int
    layout_mode: str
    reconciles_to_company_revenue: bool
    rejection_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.member_name or self.table_index < 0:
            raise ValueError("Product revenue candidate review identity is invalid")
        if self.reconciles_to_company_revenue == bool(self.rejection_reasons):
            raise ValueError("Product revenue candidate review state is inconsistent")


@dataclass(frozen=True)
class CertifiedPre2023ProductRevenueObservation:
    evidence_id: str
    period_id: str
    rcept_no: str
    source_archive_sha256: str
    member_name: str
    table_index: int
    direct_quarter_column_index: int
    direct_quarter_semantics: str
    dram_revenue_million_krw: int
    nand_revenue_million_krw: int
    other_revenue_million_krw: int
    total_revenue_million_krw: int
    company_revenue_krw: int
    product_sum_reconciled: bool = True
    company_revenue_reconciled: bool = True
    direct_product_revenue_certified: bool = True
    current_retrieval_historical_source_fact: bool = True
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    training_row_promoted: bool = False
    fit_enabled: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Certified product revenue period is unsupported")
        if len(self.evidence_id) != 64 or len(self.source_archive_sha256) != 64:
            raise ValueError("Certified product revenue hashes must be SHA-256")
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Certified product revenue receipt is invalid")
        if self.direct_quarter_column_index < 1:
            raise ValueError("Certified product revenue quarter column is invalid")
        if self.direct_quarter_semantics not in {
            "direct_quarter_3_month",
            "direct_quarter_current_period",
        }:
            raise ValueError("Certified product revenue quarter semantics are invalid")
        product_sum = (
            self.dram_revenue_million_krw
            + self.nand_revenue_million_krw
            + self.other_revenue_million_krw
        )
        if product_sum != self.total_revenue_million_krw:
            raise ValueError("Certified product revenue sum identity failed")
        if self.total_revenue_million_krw * 1_000_000 != self.company_revenue_krw:
            raise ValueError("Certified product revenue does not tie to consolidated revenue")
        if not self.product_sum_reconciled or not self.company_revenue_reconciled:
            raise ValueError("Certified product revenue reconciliation flags are incomplete")
        if not self.direct_product_revenue_certified:
            raise ValueError("Certified product revenue certification flag is false")
        if (
            not self.current_retrieval_historical_source_fact
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.training_row_promoted
            or self.fit_enabled
        ):
            raise ValueError("Certified product revenue exceeded source trust boundary")


@dataclass(frozen=True)
class Pre2023ProductRevenueCertificationResult:
    period_id: str
    certified: bool
    observation: CertifiedPre2023ProductRevenueObservation | None
    candidate_reviews: tuple[ProductRevenueCandidateReview, ...]
    error: str | None
    training_row_promoted: bool = False
    fit_enabled: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Product revenue certification period is unsupported")
        if self.certified != (self.observation is not None):
            raise ValueError("Product revenue certification success state is inconsistent")
        if self.certified == (self.error is not None):
            raise ValueError("Product revenue certification error state is inconsistent")
        if self.training_row_promoted or self.fit_enabled:
            raise ValueError("Product revenue certification exceeded model trust boundary")


def _review_candidate(
    period: ProductRevenueSourceClosurePeriod,
    candidate: ProductRevenueTableWitness,
    company: VerifiedCompanyProfitabilityConstraint,
) -> tuple[ProductRevenueCandidateReview, CertifiedPre2023ProductRevenueObservation | None]:
    reasons: list[str] = []
    try:
        if candidate.layout_mode != "structured_grid":
            raise ValueError("candidate uses diagnostic fallback layout")
        if period.rcept_no != company.rcept_no:
            raise ValueError("product and company receipts differ")
        column, semantics = _direct_quarter_column(candidate)
        dram = _amount_at(_row_for_label(candidate, _DRAM_LABELS, "DRAM"), column, "DRAM")
        nand = _amount_at(_row_for_label(candidate, _NAND_LABELS, "NAND"), column, "NAND")
        other = _amount_at(_row_for_label(candidate, _OTHER_LABELS, "other"), column, "other")
        total = _amount_at(_row_for_label(candidate, _TOTAL_LABELS, "total"), column, "total")
        if dram + nand + other != total:
            raise ValueError("DRAM + NAND + other does not equal table total")
        if total * 1_000_000 != company.revenue_krw:
            raise ValueError("table total does not equal verified consolidated revenue")
    except ValueError as exc:
        reasons.append(str(exc))
        return (
            ProductRevenueCandidateReview(
                member_name=candidate.member_name,
                table_index=candidate.table_index,
                layout_mode=candidate.layout_mode,
                reconciles_to_company_revenue=False,
                rejection_reasons=tuple(reasons),
            ),
            None,
        )

    stable = {
        "period_id": period.period_id,
        "rcept_no": period.rcept_no,
        "source_archive_sha256": period.archive_sha256,
        "member_name": candidate.member_name,
        "table_index": candidate.table_index,
        "direct_quarter_column_index": column,
        "direct_quarter_semantics": semantics,
        "dram_revenue_million_krw": dram,
        "nand_revenue_million_krw": nand,
        "other_revenue_million_krw": other,
        "total_revenue_million_krw": total,
        "company_revenue_krw": company.revenue_krw,
    }
    observation = CertifiedPre2023ProductRevenueObservation(
        evidence_id=_sha(stable),
        period_id=period.period_id,
        rcept_no=period.rcept_no,
        source_archive_sha256=period.archive_sha256,
        member_name=candidate.member_name,
        table_index=candidate.table_index,
        direct_quarter_column_index=column,
        direct_quarter_semantics=semantics,
        dram_revenue_million_krw=dram,
        nand_revenue_million_krw=nand,
        other_revenue_million_krw=other,
        total_revenue_million_krw=total,
        company_revenue_krw=company.revenue_krw,
    )
    review = ProductRevenueCandidateReview(
        member_name=candidate.member_name,
        table_index=candidate.table_index,
        layout_mode=candidate.layout_mode,
        reconciles_to_company_revenue=True,
        rejection_reasons=(),
    )
    return review, observation


def certify_pre2023_product_revenue_period(
    period: ProductRevenueSourceClosurePeriod,
    company: VerifiedCompanyProfitabilityConstraint | None,
) -> Pre2023ProductRevenueCertificationResult:
    if company is None:
        return Pre2023ProductRevenueCertificationResult(
            period_id=period.period_id,
            certified=False,
            observation=None,
            candidate_reviews=(),
            error="verified company profitability constraint is missing",
        )

    reviews: list[ProductRevenueCandidateReview] = []
    matches: list[CertifiedPre2023ProductRevenueObservation] = []
    for candidate in period.direct_separable_candidates:
        review, observation = _review_candidate(period, candidate, company)
        reviews.append(review)
        if observation is not None:
            matches.append(observation)

    if len(matches) != 1:
        return Pre2023ProductRevenueCertificationResult(
            period_id=period.period_id,
            certified=False,
            observation=None,
            candidate_reviews=tuple(reviews),
            error=(
                "direct product revenue candidate must reconcile uniquely to consolidated "
                f"company revenue: matches={len(matches)}"
            ),
        )
    return Pre2023ProductRevenueCertificationResult(
        period_id=period.period_id,
        certified=True,
        observation=matches[0],
        candidate_reviews=tuple(reviews),
        error=None,
    )


def certify_pre2023_product_revenues(
    periods: tuple[ProductRevenueSourceClosurePeriod, ...],
    company: dict[str, VerifiedCompanyProfitabilityConstraint],
) -> tuple[Pre2023ProductRevenueCertificationResult, ...]:
    by_period = {item.period_id: item for item in periods}
    if tuple(sorted(by_period)) != tuple(sorted(_EXPECTED_PERIODS)):
        raise ValueError("Pre-2023 product revenue certification periods are incomplete")
    return tuple(
        certify_pre2023_product_revenue_period(by_period[period_id], company.get(period_id))
        for period_id in _EXPECTED_PERIODS
    )


__all__ = [
    "CertifiedPre2023ProductRevenueObservation",
    "Pre2023ProductRevenueCertificationResult",
    "ProductRevenueCandidateReview",
    "certify_pre2023_product_revenue_period",
    "certify_pre2023_product_revenues",
]
