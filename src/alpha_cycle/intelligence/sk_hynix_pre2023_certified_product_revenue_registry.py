"""Canonical current-retrieval product-revenue facts for SK hynix 2021Q1-2022Q3."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml

DEFAULT_PRE2023_CERTIFIED_PRODUCT_REVENUE_REGISTRY = Path(
    "config/skhynix_pre2023_certified_product_revenue.v1.yaml"
)
_EXPECTED_PERIODS = (
    "2021Q1",
    "2021Q2",
    "2021Q3",
    "2022Q1",
    "2022Q2",
    "2022Q3",
)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Pre-2023 product registry {label} must be an object")
    return cast(dict[object, object], value)


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


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class CertifiedPre2023ProductRevenue:
    period_id: str
    rcept_no: str
    source_archive_sha256: str
    member_name: str
    table_index: int
    direct_quarter_semantics: str
    direct_quarter_column_index: int
    dram_revenue_million_krw: int
    nand_revenue_million_krw: int
    other_revenue_million_krw: int
    total_revenue_million_krw: int
    company_revenue_krw: int
    product_sum_reconciled: bool
    company_revenue_reconciled: bool
    direct_product_revenue_certified: bool

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Pre-2023 product registry period is unsupported")
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Pre-2023 product registry receipt is invalid")
        if not _valid_sha(self.source_archive_sha256):
            raise ValueError("Pre-2023 product registry source hash is invalid")
        if self.member_name != f"{self.rcept_no}.xml" or self.table_index < 0:
            raise ValueError("Pre-2023 product registry source locator is invalid")
        quarter = int(self.period_id[-1])
        expected_semantics = (
            "direct_quarter_current_period" if quarter == 1 else "direct_quarter_3_month"
        )
        if self.direct_quarter_semantics != expected_semantics:
            raise ValueError("Pre-2023 product registry direct-quarter semantics drifted")
        if self.direct_quarter_column_index != 1:
            raise ValueError("Pre-2023 product registry must use the direct current-quarter column")
        amounts = (
            self.dram_revenue_million_krw,
            self.nand_revenue_million_krw,
            self.other_revenue_million_krw,
            self.total_revenue_million_krw,
            self.company_revenue_krw,
        )
        if any(value <= 0 for value in amounts):
            raise ValueError("Pre-2023 product registry amounts must be positive")
        product_sum = (
            self.dram_revenue_million_krw
            + self.nand_revenue_million_krw
            + self.other_revenue_million_krw
        )
        if product_sum != self.total_revenue_million_krw:
            raise ValueError("Pre-2023 product registry product sum does not reconcile")
        if self.total_revenue_million_krw * 1_000_000 != self.company_revenue_krw:
            raise ValueError("Pre-2023 product registry company revenue does not reconcile")
        if not (
            self.product_sum_reconciled
            and self.company_revenue_reconciled
            and self.direct_product_revenue_certified
        ):
            raise ValueError("Pre-2023 product registry certification flags are incomplete")


@dataclass(frozen=True)
class CertifiedPre2023ProductRevenueRegistry:
    registry_id: str
    registry_version: str
    ticker: str
    periods: tuple[CertifiedPre2023ProductRevenue, ...]
    manifest_sha256: str
    current_retrieval_historical_source_fact: bool
    historical_vintage_certified: bool
    point_in_time_backtest_eligible: bool
    training_row_promoted: bool
    fit_enabled: bool
    holdout_evaluation_allowed: bool

    def __post_init__(self) -> None:
        if self.registry_id != "skhynix_pre2023_certified_product_revenue":
            raise ValueError("Pre-2023 product registry id is unsupported")
        if self.registry_version != "1.0" or self.ticker != "000660":
            raise ValueError("Pre-2023 product registry identity drifted")
        if tuple(item.period_id for item in self.periods) != _EXPECTED_PERIODS:
            raise ValueError("Pre-2023 product registry periods are incomplete")
        if len({item.rcept_no for item in self.periods}) != len(self.periods):
            raise ValueError("Pre-2023 product registry receipts must be unique")
        if not _valid_sha(self.manifest_sha256):
            raise ValueError("Pre-2023 product registry manifest hash is invalid")
        if (
            not self.current_retrieval_historical_source_fact
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.training_row_promoted
            or self.fit_enabled
            or self.holdout_evaluation_allowed
        ):
            raise ValueError("Pre-2023 product registry exceeded source trust boundary")


def _period(item: dict[object, object]) -> CertifiedPre2023ProductRevenue:
    return CertifiedPre2023ProductRevenue(
        period_id=str(item.get("period_id", "")),
        rcept_no=str(item.get("rcept_no", "")),
        source_archive_sha256=str(item.get("source_archive_sha256", "")),
        member_name=str(item.get("member_name", "")),
        table_index=int(str(item.get("table_index", -1))),
        direct_quarter_semantics=str(item.get("direct_quarter_semantics", "")),
        direct_quarter_column_index=int(str(item.get("direct_quarter_column_index", -1))),
        dram_revenue_million_krw=int(str(item.get("dram_revenue_million_krw", 0))),
        nand_revenue_million_krw=int(str(item.get("nand_revenue_million_krw", 0))),
        other_revenue_million_krw=int(str(item.get("other_revenue_million_krw", 0))),
        total_revenue_million_krw=int(str(item.get("total_revenue_million_krw", 0))),
        company_revenue_krw=int(str(item.get("company_revenue_krw", 0))),
        product_sum_reconciled=item.get("product_sum_reconciled") is True,
        company_revenue_reconciled=item.get("company_revenue_reconciled") is True,
        direct_product_revenue_certified=item.get("direct_product_revenue_certified") is True,
    )


def load_certified_pre2023_product_revenue_registry(
    path: str | Path = DEFAULT_PRE2023_CERTIFIED_PRODUCT_REVENUE_REGISTRY,
) -> CertifiedPre2023ProductRevenueRegistry:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Pre-2023 product registry schema is invalid")
    registry = _mapping(root.get("registry"), "registry")
    raw_periods = registry.get("periods")
    if not isinstance(raw_periods, list):
        raise ValueError("Pre-2023 product registry periods must be an array")
    periods = tuple(_period(_mapping(item, "period")) for item in raw_periods)
    boundary = _mapping(registry.get("source_boundary"), "source_boundary")
    stable = {
        "registry_id": registry.get("registry_id"),
        "registry_version": registry.get("registry_version"),
        "ticker": registry.get("ticker"),
        "unit": registry.get("unit"),
        "periods": [asdict(item) for item in periods],
        "source_boundary": boundary,
    }
    return CertifiedPre2023ProductRevenueRegistry(
        registry_id=str(registry.get("registry_id", "")),
        registry_version=str(registry.get("registry_version", "")),
        ticker=str(registry.get("ticker", "")).zfill(6),
        periods=periods,
        manifest_sha256=_sha(stable),
        current_retrieval_historical_source_fact=(
            boundary.get("current_retrieval_historical_source_fact") is True
        ),
        historical_vintage_certified=boundary.get("historical_vintage_certified") is True,
        point_in_time_backtest_eligible=(
            boundary.get("point_in_time_backtest_eligible") is True
        ),
        training_row_promoted=boundary.get("training_row_promoted") is True,
        fit_enabled=boundary.get("fit_enabled") is True,
        holdout_evaluation_allowed=boundary.get("holdout_evaluation_allowed") is True,
    )


__all__ = [
    "DEFAULT_PRE2023_CERTIFIED_PRODUCT_REVENUE_REGISTRY",
    "CertifiedPre2023ProductRevenue",
    "CertifiedPre2023ProductRevenueRegistry",
    "load_certified_pre2023_product_revenue_registry",
]
