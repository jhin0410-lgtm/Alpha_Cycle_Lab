"""Expand the SK hynix ex-ante PIT panel without reading historical targets.

The expansion is deliberately source-only. It reacquires immutable OpenDART filing
artifacts for four fixed 2021-2022 source quarters and then tries legacy source-year pairs
in a preregistered order. A legacy year is selected only when both Q1 and Q2 filings pass
the same receipt, byte-hash, timing, direct-product-row, and company/product reconciliation
contract. No target value, benchmark score, or estimator result is available to this module.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    load_frozen_ex_ante_estimator_selection,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER,
    ExAnteFeatureFrontier,
    load_ex_ante_feature_frontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_lagged_filing import (
    DEFAULT_LAGGED_FILING_BUNDLE,
    DEFAULT_LAGGED_FILING_CERTIFICATION,
    LaggedFilingPeriodCertification,
    LaggedFilingSourceRecord,
    build_locked_pit_feature_bundle,
    load_lagged_filing_certification_contract,
    persist_locked_pit_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    PointInTimeFeatureBundle,
    PointInTimeFeatureObservation,
    load_point_in_time_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    FrozenCompanyGPExAnteProtocol,
    load_frozen_company_gp_ex_ante_protocol,
    quarter_end,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_capture import (
    capture_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY,
    load_quarterly_company_profitability_registry,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
    load_product_revenue_probe_template,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION = Path(
    "config/skhynix_company_gp_ex_ante_pit_panel_expansion.v1.yaml"
)
DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-pit-panel-expansion"
)
DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE = (
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_OUTPUT / "latest_combined_feature_bundle.json"
)
DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT = (
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_OUTPUT / "latest_expansion_report.json"
)
_DEFAULT_COMPANY_OUTPUT = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_OUTPUT / "company"
_DEFAULT_PRODUCT_OUTPUT = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_OUTPUT / "product"
_FEATURE_IDS = (
    "lagged_company_revenue",
    "lagged_company_gross_profit",
    "lagged_company_gross_margin",
    "lagged_nand_revenue_share",
    "lagged_other_revenue_share",
)
_FIXED_SOURCE_PERIODS = ("2021Q1", "2021Q2", "2022Q1", "2022Q2")
_PRIMARY_LEGACY_YEAR = 2016
_FALLBACK_LEGACY_YEARS = (2015, 2014)
_KOREA_TZ = ZoneInfo("Asia/Seoul")
_ALLOWED_STATEMENTS = frozenset({"IS", "CIS"})


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"PIT panel expansion {label} must be an object")
    return cast(dict[object, object], value)


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"PIT panel expansion {label} must be an array")
    return value


def _integral_krw(value: object, label: str) -> int:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        raise ValueError(f"PIT panel expansion {label} is missing")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"PIT panel expansion {label} is not numeric") from exc
    if negative:
        amount = -amount
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"PIT panel expansion {label} must be integral KRW")
    return int(amount)


def _receipt_date(rcept_no: str) -> date:
    if len(rcept_no) != 14 or not rcept_no.isdigit():
        raise ValueError("PIT panel expansion receipt number must be 14 digits")
    return date(int(rcept_no[:4]), int(rcept_no[4:6]), int(rcept_no[6:8]))


def _source_available_at(receipt_date: date) -> datetime:
    return datetime.combine(receipt_date, time(23, 59, 59), tzinfo=_KOREA_TZ)


def _period_start(period_id: str) -> date:
    end = quarter_end(period_id)
    quarter = int(period_id[-1])
    month = 1 + (quarter - 1) * 3
    return date(end.year, month, 1)


def _report_name(period_id: str) -> str:
    year = int(period_id[:4])
    quarter = int(period_id[-1])
    if quarter == 1:
        return f"분기보고서 ({year}.03)"
    if quarter == 2:
        return f"반기보고서 ({year}.06)"
    raise ValueError("PIT panel expansion only supports Q1/Q2 source filings")


@dataclass(frozen=True)
class PITPanelExpansionMapping:
    source_period: str
    target_period: str
    report_code: str
    expected_receipt: str | None

    def __post_init__(self) -> None:
        source_year = int(self.source_period[:4])
        target_year = int(self.target_period[:4])
        source_quarter = int(self.source_period[-1])
        target_quarter = int(self.target_period[-1])
        if source_year != target_year or target_quarter != source_quarter + 1:
            raise ValueError("PIT panel expansion mapping must be adjacent same-year quarters")
        expected_code = {1: "11013", 2: "11012"}.get(source_quarter)
        if self.report_code != expected_code:
            raise ValueError("PIT panel expansion report code does not match source quarter")
        if self.expected_receipt is not None:
            if len(self.expected_receipt) != 14 or not self.expected_receipt.isdigit():
                raise ValueError("PIT panel expansion expected receipt must be 14 digits")


@dataclass(frozen=True)
class FrozenPITPanelExpansionContract:
    evidence_id: str
    expansion_id: str
    expansion_version: str
    status: str
    ticker: str
    scientific_scope: str
    base_bundle_evidence_id: str
    estimator_freeze_evidence_id: str
    base_certification_contract_evidence_id: str
    feature_ids: tuple[str, ...]
    primary_mappings: tuple[PITPanelExpansionMapping, ...]
    fallback_mappings: tuple[PITPanelExpansionMapping, ...]
    required_base_rows: int
    required_base_observations: int
    required_additional_rows: int
    required_total_rows: int
    required_total_observations: int
    discovery_window_days: int
    company_product_reconciliation_tolerance_krw: int

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.base_bundle_evidence_id,
            self.estimator_freeze_evidence_id,
            self.base_certification_contract_evidence_id,
        )
        if any(not _valid_sha(value) for value in hashes):
            raise ValueError("PIT panel expansion bindings must be SHA-256")
        if self.expansion_id != "skhynix_company_gp_ex_ante_pit_panel_expansion":
            raise ValueError("PIT panel expansion id drifted")
        if self.expansion_version != "1.0-frozen-pre-source-replay":
            raise ValueError("PIT panel expansion version drifted")
        if self.status != "frozen_pre_source_replay":
            raise ValueError("PIT panel expansion is not frozen before source replay")
        if self.ticker != "000660":
            raise ValueError("PIT panel expansion ticker drifted")
        if self.scientific_scope != "target_blind_pit_feature_panel_expansion_only":
            raise ValueError("PIT panel expansion scientific scope drifted")
        if self.feature_ids != _FEATURE_IDS:
            raise ValueError("PIT panel expansion feature set drifted")
        if tuple(item.source_period for item in self.primary_mappings) != (
            "2021Q1",
            "2021Q2",
            "2022Q1",
            "2022Q2",
            "2016Q1",
            "2016Q2",
        ):
            raise ValueError("PIT panel expansion primary mapping order drifted")
        if tuple(item.source_period for item in self.fallback_mappings) != (
            "2015Q1",
            "2015Q2",
            "2014Q1",
            "2014Q2",
        ):
            raise ValueError("PIT panel expansion fallback order drifted")
        if (
            self.required_base_rows != 14
            or self.required_base_observations != 70
            or self.required_additional_rows != 6
            or self.required_total_rows != 20
            or self.required_total_observations != 100
        ):
            raise ValueError("PIT panel expansion geometry drifted")
        if self.discovery_window_days != 120:
            raise ValueError("PIT panel expansion discovery window drifted")
        if self.company_product_reconciliation_tolerance_krw != 1_000_000:
            raise ValueError("PIT panel expansion reconciliation tolerance drifted")

    @property
    def fixed_mappings(self) -> tuple[PITPanelExpansionMapping, ...]:
        return self.primary_mappings[:4]

    @property
    def primary_legacy_pair(self) -> tuple[PITPanelExpansionMapping, ...]:
        return self.primary_mappings[4:]

    @property
    def legacy_year_priority(self) -> tuple[int, ...]:
        return (_PRIMARY_LEGACY_YEAR, *_FALLBACK_LEGACY_YEARS)

    def mappings_for_legacy_year(self, year: int) -> tuple[PITPanelExpansionMapping, ...]:
        candidates = (*self.primary_legacy_pair, *self.fallback_mappings)
        result = tuple(item for item in candidates if int(item.source_period[:4]) == year)
        if len(result) != 2:
            raise ValueError(f"PIT panel expansion legacy year mapping is incomplete: {year}")
        return result


@dataclass(frozen=True)
class ExpansionSourceAttempt:
    source_period: str
    target_period: str
    success: bool
    receipt_no: str | None
    receipt_date: str | None
    company_raw_bytes_sha256: str | None
    product_archive_sha256: str | None
    error_type: str | None
    error: str | None
    target_value_read: bool = False
    estimator_fit_run: bool = False
    backtest_run: bool = False

    def __post_init__(self) -> None:
        if self.success:
            required = (
                self.receipt_no,
                self.receipt_date,
                self.company_raw_bytes_sha256,
                self.product_archive_sha256,
            )
            if any(value is None for value in required):
                raise ValueError("Successful PIT expansion attempt lacks source identity")
            if self.error_type is not None or self.error is not None:
                raise ValueError("Successful PIT expansion attempt cannot retain an error")
        elif self.error_type is None or self.error is None:
            raise ValueError("Failed PIT expansion attempt must retain an error")
        if self.target_value_read or self.estimator_fit_run or self.backtest_run:
            raise ValueError("PIT expansion attempt exceeded source-only boundary")


@dataclass(frozen=True)
class ExpansionRunResult:
    contract_evidence_id: str
    base_bundle_evidence_id: str
    selected_legacy_year: int | None
    attempts: tuple[ExpansionSourceAttempt, ...]
    added_target_periods: tuple[str, ...]
    added_target_row_count: int
    added_feature_observation_count: int
    combined_target_periods: tuple[str, ...]
    combined_target_row_count: int
    combined_feature_observation_count: int
    combined_bundle_evidence_id: str | None
    eligible_added_observation_count: int
    rejected_added_observation_count: int
    all_added_observations_point_in_time_eligible: bool
    completion_gate_passed: bool
    status: str
    next_action: str
    historical_target_values_read: bool = False
    target_join_authorized: bool = False
    estimator_fit_authorized: bool = False
    historical_backtest_run: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.contract_evidence_id) or not _valid_sha(
            self.base_bundle_evidence_id
        ):
            raise ValueError("PIT expansion result evidence binding is invalid")
        if self.combined_bundle_evidence_id is not None and not _valid_sha(
            self.combined_bundle_evidence_id
        ):
            raise ValueError("PIT expansion combined bundle evidence id is invalid")
        if self.added_feature_observation_count != 5 * self.added_target_row_count:
            raise ValueError("PIT expansion added dimensions do not reconcile")
        if self.combined_feature_observation_count != 5 * self.combined_target_row_count:
            raise ValueError("PIT expansion combined dimensions do not reconcile")
        if self.all_added_observations_point_in_time_eligible != (
            self.rejected_added_observation_count == 0
        ):
            raise ValueError("PIT expansion eligibility flag is inconsistent")
        prohibited = (
            self.historical_target_values_read,
            self.target_join_authorized,
            self.estimator_fit_authorized,
            self.historical_backtest_run,
            self.q3_target_read,
            self.q3_source_outcome_loaded,
        )
        if any(prohibited):
            raise ValueError("PIT expansion result exceeded target-blind boundary")
        expected_complete = (
            self.selected_legacy_year in {_PRIMARY_LEGACY_YEAR, *_FALLBACK_LEGACY_YEARS}
            and self.added_target_row_count == 6
            and self.added_feature_observation_count == 30
            and self.combined_target_row_count == 20
            and self.combined_feature_observation_count == 100
            and self.eligible_added_observation_count == 30
            and self.rejected_added_observation_count == 0
            and self.combined_bundle_evidence_id is not None
        )
        if self.completion_gate_passed != expected_complete:
            raise ValueError("PIT expansion completion gate flag is inconsistent")
        expected_status = (
            "skhynix_ex_ante_pit_panel_expansion_complete_target_blind"
            if self.completion_gate_passed
            else "skhynix_ex_ante_pit_panel_expansion_incomplete_target_blind"
        )
        if self.status != expected_status:
            raise ValueError("PIT expansion status is inconsistent")


def _mapping_from_raw(item: object) -> PITPanelExpansionMapping:
    row = _mapping(item, "source mapping")
    expected_raw = row.get("expected_receipt")
    return PITPanelExpansionMapping(
        source_period=str(row.get("source_period", "")),
        target_period=str(row.get("target_period", "")),
        report_code=str(row.get("report_code", "")),
        expected_receipt=(
            None if expected_raw in {None, ""} else str(expected_raw).strip()
        ),
    )


def load_frozen_pit_panel_expansion_contract(
    path: str | Path = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION,
) -> FrozenPITPanelExpansionContract:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("PIT panel expansion schema is invalid")
    body = _mapping(root.get("expansion"), "body")
    bindings = _mapping(body.get("bindings"), "bindings")
    geometry = _mapping(body.get("panel_geometry"), "panel_geometry")
    source_contract = _mapping(body.get("source_contract"), "source_contract")
    acquisition = _mapping(body.get("acquisition_policy"), "acquisition_policy")
    trust = _mapping(body.get("trust_boundary"), "trust_boundary")
    primary = tuple(
        _mapping_from_raw(item)
        for item in _array(body.get("primary_source_to_target_mappings"), "primary mappings")
    )
    fallback_policy = _mapping(
        body.get("source_only_fallback_policy"), "source_only_fallback_policy"
    )
    fallback = tuple(
        _mapping_from_raw(item)
        for item in _array(fallback_policy.get("fallback_order"), "fallback order")
    )
    if fallback_policy.get("selection_rule") != "first_complete_source_year_pair_in_frozen_order":
        raise ValueError("PIT panel expansion fallback selection rule drifted")
    if fallback_policy.get("partial_year_pair_selection_allowed") is True:
        raise ValueError("PIT panel expansion cannot select a partial legacy year")
    if acquisition.get("product_discovery_window_method") != (
        "period_end_plus_1_day_through_period_end_plus_120_days"
    ):
        raise ValueError("PIT panel expansion discovery method drifted")
    if acquisition.get("product_discovery_window_may_be_tuned_by_year_after_source_replay") is True:
        raise ValueError("PIT panel expansion discovery window cannot be tuned after replay")
    if acquisition.get("exact_periodic_report_name_required") is not True:
        raise ValueError("PIT panel expansion requires exact report names")
    if acquisition.get("correction_disclosures_allowed") is True:
        raise ValueError("PIT panel expansion corrections must remain disallowed")
    if source_contract.get("inferred_or_synthetic_product_allocation_allowed") is True:
        raise ValueError("PIT panel expansion cannot synthesize product allocation")
    if any(value is True for value in trust.values()):
        raise ValueError("PIT panel expansion manifest opened a prohibited trust flag")
    feature_ids = tuple(
        str(item) for item in _array(body.get("frozen_feature_ids"), "feature ids")
    )
    stable = {"schema_version": root["schema_version"], "expansion": body}
    return FrozenPITPanelExpansionContract(
        evidence_id=_sha(stable),
        expansion_id=str(body.get("expansion_id", "")),
        expansion_version=str(body.get("expansion_version", "")),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        scientific_scope=str(body.get("scientific_scope", "")),
        base_bundle_evidence_id=str(bindings.get("base_bundle_evidence_id", "")),
        estimator_freeze_evidence_id=str(bindings.get("estimator_freeze_evidence_id", "")),
        base_certification_contract_evidence_id=str(
            bindings.get("base_certification_contract_evidence_id", "")
        ),
        feature_ids=feature_ids,
        primary_mappings=primary,
        fallback_mappings=fallback,
        required_base_rows=int(str(geometry.get("base_target_row_count", -1))),
        required_base_observations=int(
            str(geometry.get("base_feature_observation_count", -1))
        ),
        required_additional_rows=int(
            str(geometry.get("required_additional_target_rows", -1))
        ),
        required_total_rows=int(
            str(geometry.get("required_total_target_rows_before_first_target_join", -1))
        ),
        required_total_observations=int(
            str(geometry.get("required_total_feature_observations", -1))
        ),
        discovery_window_days=120,
        company_product_reconciliation_tolerance_krw=int(
            str(source_contract.get("company_product_revenue_reconciliation_tolerance_krw", -1))
        ),
    )


def _financial_rows(raw_payload: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_payload, dict):
        raise ValueError("PIT expansion company payload must be an object")
    financials = cast(dict[object, object], raw_payload).get("financials")
    if not isinstance(financials, dict):
        raise ValueError("PIT expansion company payload lacks financials")
    raw_rows = cast(dict[object, object], financials).get("list")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("PIT expansion company financial list is empty")
    result: list[dict[str, object]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise ValueError("PIT expansion company financial row must be an object")
        result.append(
            {str(key): value for key, value in cast(dict[object, object], raw_row).items()}
        )
    return tuple(result)


def _select_company_account(
    rows: tuple[dict[str, object], ...],
    account_ids: tuple[str, ...],
    mapping: PITPanelExpansionMapping,
    *,
    label: str,
) -> tuple[int, str]:
    accepted = {item.casefold() for item in account_ids}
    year = int(mapping.source_period[:4])
    matches: list[tuple[int, str]] = []
    for row in rows:
        if str(row.get("sj_div", "")).strip() not in _ALLOWED_STATEMENTS:
            continue
        if str(row.get("account_id", "")).strip().casefold() not in accepted:
            continue
        row_year = str(row.get("bsns_year", "")).strip()
        row_code = str(row.get("reprt_code", "")).strip()
        if row_year and row_year != str(year):
            continue
        if row_code and row_code != mapping.report_code:
            continue
        receipt = str(row.get("rcept_no", "")).strip()
        _receipt_date(receipt)
        matches.append((_integral_krw(row.get("thstrm_amount"), label), receipt))
    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise ValueError(
            f"PIT expansion company account must resolve uniquely: "
            f"{mapping.source_period} {label} count={len(unique)}"
        )
    return unique[0]


@dataclass(frozen=True)
class _CompanyCapture:
    rcept_no: str
    receipt_date: date
    revenue_krw: int
    gross_profit_krw: int
    raw_payload_sha256: str
    raw_path: Path
    raw_bytes_sha256: str


def _capture_company_source(
    client: OpenDartReadOnlyClient,
    mapping: PITPanelExpansionMapping,
    *,
    evaluation_date: date,
    output: Path,
) -> _CompanyCapture:
    template = load_quarterly_company_profitability_registry(
        DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY
    )
    corp = client.resolve_stock_codes([template.ticker])[template.ticker]
    batch = client.financial_statements(
        corp,
        business_year=int(mapping.source_period[:4]),
        report_code=mapping.report_code,
        fs_div=template.fs_div,
    )
    raw_payload = batch.raw_payload
    rows = _financial_rows(raw_payload)
    revenue, revenue_receipt = _select_company_account(
        rows, template.revenue_account_ids, mapping, label="revenue"
    )
    cost, cost_receipt = _select_company_account(
        rows, template.cost_of_sales_account_ids, mapping, label="cost_of_sales"
    )
    gross, gross_receipt = _select_company_account(
        rows, template.gross_profit_account_ids, mapping, label="gross_profit"
    )
    receipts = {revenue_receipt, cost_receipt, gross_receipt}
    if len(receipts) != 1:
        raise ValueError("PIT expansion company accounts cross filing receipts")
    receipt = next(iter(receipts))
    receipt_date = _receipt_date(receipt)
    if mapping.expected_receipt is not None and receipt != mapping.expected_receipt:
        raise ValueError(
            f"PIT expansion company receipt does not match frozen receipt: "
            f"{mapping.source_period} actual={receipt} expected={mapping.expected_receipt}"
        )
    if receipt_date > evaluation_date:
        raise ValueError("PIT expansion company source is future-dated")
    if revenue - cost != gross:
        raise ValueError(
            f"PIT expansion company accounting identity failed: {mapping.source_period}"
        )
    period_root = output / mapping.source_period
    period_root.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(UTC)
    raw_path = period_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__raw_payload.json"
    )
    raw_bytes = json.dumps(
        raw_payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    raw_path.write_bytes(raw_bytes)
    return _CompanyCapture(
        rcept_no=receipt,
        receipt_date=receipt_date,
        revenue_krw=revenue,
        gross_profit_krw=gross,
        raw_payload_sha256=_sha(raw_payload),
        raw_path=raw_path,
        raw_bytes_sha256=_sha_bytes(raw_bytes),
    )


def build_expansion_product_spec(
    contract: FrozenPITPanelExpansionContract,
    mapping: PITPanelExpansionMapping,
    *,
    template_registry: str | Path = DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
) -> PeriodicProductRevenueSpec:
    template = load_product_revenue_probe_template(template_registry)
    period_end = quarter_end(mapping.source_period)
    return PeriodicProductRevenueSpec(
        document_id=(
            f"skhynix_000660_{mapping.source_period.casefold()}_"
            "ex_ante_pit_expansion"
        ),
        ticker=contract.ticker,
        issuer_name=template.issuer_name,
        source_id="opendart",
        report_name_exact=_report_name(mapping.source_period),
        discovery_begin_date=period_end + timedelta(days=1),
        discovery_end_date=period_end + timedelta(days=contract.discovery_window_days),
        period_start=_period_start(mapping.source_period),
        period_end=period_end,
        parser_id=template.parser_id,
        expected_identity_anchors=template.expected_identity_anchors,
        product_labels=template.product_labels,
    )


def _acquire_source_record(
    client: OpenDartReadOnlyClient,
    contract: FrozenPITPanelExpansionContract,
    protocol: FrozenCompanyGPExAnteProtocol,
    mapping: PITPanelExpansionMapping,
    *,
    evaluation_date: date,
    company_output: Path,
    product_output: Path,
    template_registry: str | Path,
) -> tuple[LaggedFilingSourceRecord, ExpansionSourceAttempt]:
    company = _capture_company_source(
        client,
        mapping,
        evaluation_date=evaluation_date,
        output=company_output,
    )
    if _source_available_at(company.receipt_date) > protocol.origin_for(mapping.target_period):
        raise ValueError(
            f"PIT expansion company source misses target forecast origin: "
            f"{mapping.source_period}->{mapping.target_period}"
        )
    spec = build_expansion_product_spec(contract, mapping, template_registry=template_registry)
    period_product_output = product_output / mapping.source_period
    capture_periodic_product_revenue_certification(
        client,
        spec,
        evaluation_date=evaluation_date,
        output=period_product_output,
    )
    pointer_path = period_product_output / "latest_certification.json"
    product = load_periodic_product_revenue_certification(
        pointer_path,
        evaluation_date=evaluation_date,
    )
    pointer_raw: object = json.loads(pointer_path.read_text(encoding="utf-8"))
    if not isinstance(pointer_raw, dict):
        raise ValueError("PIT expansion product pointer must be an object")
    pointer = {str(key): value for key, value in cast(dict[object, object], pointer_raw).items()}
    archive_path = Path(str(pointer.get("archive_path", "")))
    if not archive_path.is_file():
        raise ValueError("PIT expansion product archive is missing")
    if mapping.expected_receipt is not None and product.rcept_no != mapping.expected_receipt:
        raise ValueError(
            f"PIT expansion product receipt does not match frozen receipt: "
            f"{mapping.source_period} actual={product.rcept_no} "
            f"expected={mapping.expected_receipt}"
        )
    if product.rcept_no != company.rcept_no:
        raise ValueError(
            f"PIT expansion company/product receipt mismatch: {mapping.source_period}"
        )
    if product.receipt_date != company.receipt_date:
        raise ValueError(
            f"PIT expansion company/product receipt-date mismatch: {mapping.source_period}"
        )
    if _sha_bytes(archive_path.read_bytes()) != product.archive_sha256:
        raise ValueError(f"PIT expansion product archive hash mismatch: {mapping.source_period}")
    gap_krw = abs(
        company.revenue_krw
        - int(round(float(product.metrics.reported_company_revenue) * 1_000_000.0))
    )
    if gap_krw > contract.company_product_reconciliation_tolerance_krw:
        raise ValueError(
            f"PIT expansion company/product revenue reconciliation failed: "
            f"{mapping.source_period} gap_krw={gap_krw}"
        )
    record = LaggedFilingSourceRecord(
        source_period=mapping.source_period,
        target_period=mapping.target_period,
        rcept_no=company.rcept_no,
        receipt_date=company.receipt_date,
        company_revenue_krw=company.revenue_krw,
        company_gross_profit_krw=company.gross_profit_krw,
        company_raw_payload_sha256=company.raw_payload_sha256,
        company_raw_path=str(company.raw_path.resolve()),
        product_evidence_id=product.evidence_id,
        product_archive_sha256=product.archive_sha256,
        product_archive_path=str(archive_path.resolve()),
        nand_revenue_krw_million=float(product.metrics.nand_and_solutions),
        other_revenue_krw_million=float(product.metrics.other_products_services),
        product_total_revenue_krw_million=float(product.metrics.reported_company_revenue),
    )
    attempt = ExpansionSourceAttempt(
        source_period=mapping.source_period,
        target_period=mapping.target_period,
        success=True,
        receipt_no=company.rcept_no,
        receipt_date=company.receipt_date.isoformat(),
        company_raw_bytes_sha256=company.raw_bytes_sha256,
        product_archive_sha256=product.archive_sha256,
        error_type=None,
        error=None,
    )
    return record, attempt


def certify_expansion_source_record(
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
    record: LaggedFilingSourceRecord,
) -> LaggedFilingPeriodCertification:
    source_available_at = _source_available_at(record.receipt_date)
    if source_available_at > protocol.origin_for(record.target_period):
        raise ValueError(
            f"PIT expansion source was unavailable by forecast origin: {record.source_period}"
        )
    company_path = Path(record.company_raw_path)
    company_bytes = company_path.read_bytes()
    company_bytes_sha = _sha_bytes(company_bytes)
    company_payload: object = json.loads(company_bytes.decode("utf-8"))
    if _sha(company_payload) != record.company_raw_payload_sha256:
        raise ValueError(
            f"PIT expansion company canonical payload hash mismatch: {record.source_period}"
        )
    product_bytes = Path(record.product_archive_path).read_bytes()
    if _sha_bytes(product_bytes) != record.product_archive_sha256:
        raise ValueError(
            f"PIT expansion product archive hash mismatch: {record.source_period}"
        )
    company_revenue_million = record.company_revenue_krw / 1_000_000.0
    if abs(company_revenue_million - record.product_total_revenue_krw_million) > 1.0:
        raise ValueError(
            f"PIT expansion company/product revenue gap exceeds 1 KRW million: "
            f"{record.source_period}"
        )
    company_gp_million = record.company_gross_profit_krw / 1_000_000.0
    gross_margin = record.company_gross_profit_krw / record.company_revenue_krw
    nand_share = record.nand_revenue_krw_million / record.product_total_revenue_krw_million
    other_share = record.other_revenue_krw_million / record.product_total_revenue_krw_million
    if not all(math.isfinite(value) for value in (gross_margin, nand_share, other_share)):
        raise ValueError("PIT expansion deterministic feature transform is non-finite")
    if not 0.0 <= nand_share <= 1.0 or not 0.0 <= other_share <= 1.0:
        raise ValueError("PIT expansion product share is outside [0,1]")
    company_evidence_id = _sha(
        {
            "source_period": record.source_period,
            "rcept_no": record.rcept_no,
            "receipt_date": record.receipt_date.isoformat(),
            "raw_bytes_sha256": company_bytes_sha,
            "raw_payload_sha256": record.company_raw_payload_sha256,
            "company_revenue_krw": record.company_revenue_krw,
            "company_gross_profit_krw": record.company_gross_profit_krw,
        }
    )
    version = f"opendart_rcept_no:{record.rcept_no};source_period:{record.source_period}"
    raw_observations = (
        ("lagged_company_revenue", company_revenue_million, company_bytes_sha, company_evidence_id, True),
        ("lagged_company_gross_profit", company_gp_million, company_bytes_sha, company_evidence_id, True),
        ("lagged_company_gross_margin", gross_margin, company_bytes_sha, company_evidence_id, False),
        (
            "lagged_nand_revenue_share",
            nand_share,
            record.product_archive_sha256,
            record.product_evidence_id,
            False,
        ),
        (
            "lagged_other_revenue_share",
            other_share,
            record.product_archive_sha256,
            record.product_evidence_id,
            False,
        ),
    )
    feature_map = frontier.by_id()
    observations: list[PointInTimeFeatureObservation] = []
    for feature_id, value, bytes_sha, evidence_id, direct in raw_observations:
        feature = feature_map.get(feature_id)
        if feature is None:
            raise ValueError(f"PIT expansion feature is absent from frontier: {feature_id}")
        if "timestamped_immutable_filing" not in feature.acceptable_provenance_classes:
            raise ValueError(
                f"PIT expansion feature forbids immutable filing provenance: {feature_id}"
            )
        observations.append(
            PointInTimeFeatureObservation(
                period_id=record.target_period,
                feature_id=feature_id,
                value=float(value),
                provenance_class="timestamped_immutable_filing",
                source_available_at=source_available_at,
                source_bytes_sha256=bytes_sha,
                source_evidence_id=evidence_id,
                source_version_identity=version,
                direct_source_fact=direct,
                deterministic_transform=not direct,
                target_metric_in_payload=False,
            )
        )
    ordered = tuple(observations)
    if tuple(item.feature_id for item in ordered) != _FEATURE_IDS:
        raise ValueError("PIT expansion observation feature order drifted")
    return LaggedFilingPeriodCertification(
        source_period=record.source_period,
        target_period=record.target_period,
        rcept_no=record.rcept_no,
        source_available_at=source_available_at,
        company_raw_bytes_sha256=company_bytes_sha,
        product_archive_sha256=record.product_archive_sha256,
        feature_ids=_FEATURE_IDS,
        observations=ordered,
    )


def _attempt_mapping(
    client: OpenDartReadOnlyClient,
    contract: FrozenPITPanelExpansionContract,
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
    mapping: PITPanelExpansionMapping,
    *,
    evaluation_date: date,
    company_output: Path,
    product_output: Path,
    template_registry: str | Path,
) -> tuple[ExpansionSourceAttempt, LaggedFilingPeriodCertification | None]:
    try:
        record, attempt = _acquire_source_record(
            client,
            contract,
            protocol,
            mapping,
            evaluation_date=evaluation_date,
            company_output=company_output,
            product_output=product_output,
            template_registry=template_registry,
        )
        certification = certify_expansion_source_record(protocol, frontier, record)
        return attempt, certification
    except Exception as exc:
        return (
            ExpansionSourceAttempt(
                source_period=mapping.source_period,
                target_period=mapping.target_period,
                success=False,
                receipt_no=None,
                receipt_date=None,
                company_raw_bytes_sha256=None,
                product_archive_sha256=None,
                error_type=type(exc).__name__,
                error=str(exc),
            ),
            None,
        )


def select_first_complete_legacy_year(
    contract: FrozenPITPanelExpansionContract,
    attempts: tuple[ExpansionSourceAttempt, ...],
) -> int | None:
    by_source = {item.source_period: item for item in attempts}
    for year in contract.legacy_year_priority:
        pair = contract.mappings_for_legacy_year(year)
        if all(
            mapping.source_period in by_source
            and by_source[mapping.source_period].success
            for mapping in pair
        ):
            return year
    return None


def _validate_base_bundle(
    contract: FrozenPITPanelExpansionContract,
    bundle: PointInTimeFeatureBundle,
) -> tuple[str, ...]:
    if bundle.evidence_id != contract.base_bundle_evidence_id:
        raise ValueError("PIT expansion base bundle evidence id does not match frozen binding")
    if bundle.target_values_included:
        raise ValueError("PIT expansion base bundle unexpectedly includes targets")
    periods = tuple(sorted({item.period_id for item in bundle.observations}))
    if len(periods) != contract.required_base_rows:
        raise ValueError("PIT expansion base bundle row count drifted")
    if len(bundle.observations) != contract.required_base_observations:
        raise ValueError("PIT expansion base bundle observation count drifted")
    by_period: dict[str, list[str]] = {}
    for observation in bundle.observations:
        by_period.setdefault(observation.period_id, []).append(observation.feature_id)
    for period_id, feature_ids in by_period.items():
        if tuple(feature_ids) != contract.feature_ids:
            raise ValueError(
                f"PIT expansion base feature schema drifted for period: {period_id}"
            )
    return periods


def _compose_bundle(
    base: PointInTimeFeatureBundle,
    additions: tuple[LaggedFilingPeriodCertification, ...],
    *,
    created_at: datetime,
) -> PointInTimeFeatureBundle:
    feature_order = {feature_id: index for index, feature_id in enumerate(_FEATURE_IDS)}
    observations = tuple(
        sorted(
            (
                *base.observations,
                *(observation for item in additions for observation in item.observations),
            ),
            key=lambda item: (item.period_id, feature_order[item.feature_id]),
        )
    )
    return build_locked_pit_feature_bundle(created_at=created_at, observations=observations)


def _persist_report(result: ExpansionRunResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": result.status,
        "result": asdict(result),
    }
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def run_target_blind_pit_panel_expansion(
    client: OpenDartReadOnlyClient,
    *,
    evaluation_date: date,
    manifest: str | Path = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION,
    base_bundle_path: str | Path = DEFAULT_LAGGED_FILING_BUNDLE,
    protocol_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    feature_frontier_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER,
    estimator_freeze_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    base_certification_contract_path: str | Path = DEFAULT_LAGGED_FILING_CERTIFICATION,
    company_output: str | Path = _DEFAULT_COMPANY_OUTPUT,
    product_output: str | Path = _DEFAULT_PRODUCT_OUTPUT,
    product_template_registry: str | Path = DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
    combined_bundle_output: str | Path = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
    report_output: str | Path = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT,
    created_at: datetime | None = None,
) -> ExpansionRunResult:
    contract = load_frozen_pit_panel_expansion_contract(manifest)
    protocol = load_frozen_company_gp_ex_ante_protocol(protocol_path)
    frontier = load_ex_ante_feature_frontier(feature_frontier_path)
    estimator_freeze = load_frozen_ex_ante_estimator_selection(estimator_freeze_path)
    base_certification = load_lagged_filing_certification_contract(
        base_certification_contract_path
    )
    if estimator_freeze.evidence_id != contract.estimator_freeze_evidence_id:
        raise ValueError("PIT expansion estimator-freeze binding drifted")
    if base_certification.evidence_id != contract.base_certification_contract_evidence_id:
        raise ValueError("PIT expansion base-certification binding drifted")
    base_bundle = load_point_in_time_feature_bundle(base_bundle_path)
    base_periods = _validate_base_bundle(contract, base_bundle)

    attempts: list[ExpansionSourceAttempt] = []
    certifications: dict[str, LaggedFilingPeriodCertification] = {}
    for mapping in contract.fixed_mappings:
        attempt, certification = _attempt_mapping(
            client,
            contract,
            protocol,
            frontier,
            mapping,
            evaluation_date=evaluation_date,
            company_output=Path(company_output),
            product_output=Path(product_output),
            template_registry=product_template_registry,
        )
        attempts.append(attempt)
        if certification is not None:
            certifications[mapping.source_period] = certification

    selected_legacy_year: int | None = None
    for year in contract.legacy_year_priority:
        pair = contract.mappings_for_legacy_year(year)
        pair_attempts: list[ExpansionSourceAttempt] = []
        pair_certifications: list[LaggedFilingPeriodCertification] = []
        for mapping in pair:
            attempt, certification = _attempt_mapping(
                client,
                contract,
                protocol,
                frontier,
                mapping,
                evaluation_date=evaluation_date,
                company_output=Path(company_output),
                product_output=Path(product_output),
                template_registry=product_template_registry,
            )
            attempts.append(attempt)
            pair_attempts.append(attempt)
            if certification is not None:
                pair_certifications.append(certification)
        if all(item.success for item in pair_attempts) and len(pair_certifications) == 2:
            selected_legacy_year = year
            for item in pair_certifications:
                certifications[item.source_period] = item
            break

    selected_by_attempts = select_first_complete_legacy_year(contract, tuple(attempts))
    if selected_by_attempts != selected_legacy_year:
        raise ValueError("PIT expansion legacy-year selection replay drifted")
    selected_mappings = list(contract.fixed_mappings)
    if selected_legacy_year is not None:
        selected_mappings.extend(contract.mappings_for_legacy_year(selected_legacy_year))
    additions = tuple(
        certifications[mapping.source_period]
        for mapping in selected_mappings
        if mapping.source_period in certifications
    )
    added_periods = tuple(item.target_period for item in additions)
    added_observations = tuple(
        observation for item in additions for observation in item.observations
    )
    eligible_added = 0
    rejected_added = 0
    feature_map = frontier.by_id()
    for observation in added_observations:
        feature = feature_map.get(observation.feature_id)
        eligible = (
            feature is not None
            and observation.provenance_class in feature.acceptable_provenance_classes
            and observation.source_available_at <= protocol.origin_for(observation.period_id)
            and not observation.target_metric_in_payload
        )
        if eligible:
            eligible_added += 1
        else:
            rejected_added += 1

    combined_periods = tuple(sorted(set((*base_periods, *added_periods))))
    complete_shape = (
        len(additions) == contract.required_additional_rows
        and len(added_observations) == contract.required_additional_rows * len(_FEATURE_IDS)
        and len(combined_periods) == contract.required_total_rows
        and len(base_bundle.observations) + len(added_observations)
        == contract.required_total_observations
        and eligible_added == len(added_observations)
        and rejected_added == 0
        and selected_legacy_year is not None
    )
    combined_bundle: PointInTimeFeatureBundle | None = None
    if complete_shape:
        combined_bundle = _compose_bundle(
            base_bundle,
            additions,
            created_at=created_at or datetime.now(UTC),
        )
        if len(combined_bundle.observations) != contract.required_total_observations:
            raise ValueError("PIT expansion combined bundle observation count drifted")
        persist_locked_pit_feature_bundle(combined_bundle, combined_bundle_output)

    status = (
        "skhynix_ex_ante_pit_panel_expansion_complete_target_blind"
        if complete_shape
        else "skhynix_ex_ante_pit_panel_expansion_incomplete_target_blind"
    )
    next_action = (
        "refreeze_exact_twenty_period_ex_ante_scope_before_first_target_join"
        if complete_shape
        else "repair_only_failed_source_rows_without_reading_targets_then_replay_expansion"
    )
    result = ExpansionRunResult(
        contract_evidence_id=contract.evidence_id,
        base_bundle_evidence_id=base_bundle.evidence_id,
        selected_legacy_year=selected_legacy_year,
        attempts=tuple(attempts),
        added_target_periods=added_periods,
        added_target_row_count=len(additions),
        added_feature_observation_count=len(added_observations),
        combined_target_periods=combined_periods,
        combined_target_row_count=len(combined_periods),
        combined_feature_observation_count=(
            len(base_bundle.observations) + len(added_observations)
        ),
        combined_bundle_evidence_id=(
            None if combined_bundle is None else combined_bundle.evidence_id
        ),
        eligible_added_observation_count=eligible_added,
        rejected_added_observation_count=rejected_added,
        all_added_observations_point_in_time_eligible=rejected_added == 0,
        completion_gate_passed=complete_shape,
        status=status,
        next_action=next_action,
    )
    _persist_report(result, Path(report_output))
    return result


__all__ = [
    "DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION",
    "DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE",
    "DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_OUTPUT",
    "DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT",
    "ExpansionRunResult",
    "ExpansionSourceAttempt",
    "FrozenPITPanelExpansionContract",
    "PITPanelExpansionMapping",
    "build_expansion_product_spec",
    "certify_expansion_source_record",
    "load_frozen_pit_panel_expansion_contract",
    "run_target_blind_pit_panel_expansion",
    "select_first_complete_legacy_year",
]
