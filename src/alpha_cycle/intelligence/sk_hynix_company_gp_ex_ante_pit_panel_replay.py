"""Replay-compatible source acquisition for the frozen SK hynix ex-ante PIT expansion.

This adapter repairs two source-only mechanics discovered by the first live replay without
opening historical targets or changing the frozen row-selection rule:

* an immutable filing may be reacquired after the research evaluation date when its exact
  receipt predates the evaluation date and the target forecast origin; and
* legacy OpenDART all-accounts payloads may recover Revenue / Cost of Sales / Gross Profit
  by the exact Korean account-name set that was already registered for earlier legacy
  SK hynix recovery, but never by fuzzy matching or arithmetic reconstruction.

The original expansion contract, feature set, legacy-year priority, and 20-row completion
gate remain unchanged. Product evidence still requires exact receipt identity, archived
ZIP bytes, direct DRAM/NAND/Other/Total rows, source-consensus validation, parser-contract
binding, and company/product revenue reconciliation.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence import sk_hynix_company_gp_ex_ante_pit_panel_expansion as base
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
    load_lagged_filing_certification_contract,
    persist_locked_pit_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    PointInTimeFeatureBundle,
    load_point_in_time_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    FrozenCompanyGPExAnteProtocol,
    load_frozen_company_gp_ex_ante_protocol,
)
from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_source_consensus import (
    parse_periodic_product_revenue_source_consensus,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    OpenDartPeriodicProductRevenueCertification,
    PeriodicProductRevenueSpec,
    _payload,
    discover_periodic_product_revenue,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_contract import (
    bind_periodic_product_revenue_parser_contract,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY,
    load_quarterly_company_profitability_registry,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentArchive,
    OpenDartDisclosureDocumentClient,
)

DEFAULT_EX_ANTE_PIT_PANEL_REPLAY_OUTPUT = base.DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_OUTPUT
_DEFAULT_COMPANY_OUTPUT = DEFAULT_EX_ANTE_PIT_PANEL_REPLAY_OUTPUT / "company"
_DEFAULT_PRODUCT_OUTPUT = DEFAULT_EX_ANTE_PIT_PANEL_REPLAY_OUTPUT / "product"
_FEATURE_IDS = (
    "lagged_company_revenue",
    "lagged_company_gross_profit",
    "lagged_company_gross_margin",
    "lagged_nand_revenue_share",
    "lagged_other_revenue_share",
)
_ALLOWED_STATEMENTS = frozenset({"IS", "CIS"})
_ACCOUNT_NAMES = {
    "revenue": frozenset({"매출액", "수익(매출액)"}),
    "cost_of_sales": frozenset({"매출원가"}),
    "gross_profit": frozenset({"매출총이익"}),
}


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


def _norm(value: object) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split()).casefold()


def _integral_krw(value: object, label: str) -> int:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        raise ValueError(f"PIT replay company {label} is missing")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"PIT replay company {label} is not numeric") from exc
    if negative:
        amount = -amount
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"PIT replay company {label} must be integral KRW")
    return int(amount)


def _financial_rows(raw_payload: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_payload, dict):
        raise ValueError("PIT replay company payload must be an object")
    financials = cast(dict[object, object], raw_payload).get("financials")
    if not isinstance(financials, dict):
        raise ValueError("PIT replay company payload lacks financials")
    raw_rows = cast(dict[object, object], financials).get("list")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("PIT replay company financial list is empty")
    rows: list[dict[str, object]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise ValueError("PIT replay company financial row must be an object")
        rows.append(
            {str(key): value for key, value in cast(dict[object, object], raw_row).items()}
        )
    return tuple(rows)


def _row_matches_period(
    row: dict[str, object],
    mapping: base.PITPanelExpansionMapping,
) -> bool:
    if str(row.get("sj_div", "")).strip() not in _ALLOWED_STATEMENTS:
        return False
    year = int(mapping.source_period[:4])
    row_year = str(row.get("bsns_year", "")).strip()
    row_code = str(row.get("reprt_code", "")).strip()
    if row_year and row_year != str(year):
        return False
    return not row_code or row_code == mapping.report_code


def select_company_account_for_replay(
    rows: tuple[dict[str, object], ...],
    account_ids: tuple[str, ...],
    mapping: base.PITPanelExpansionMapping,
    *,
    label: str,
) -> tuple[int, str, str]:
    """Select one direct account, falling back only to preregistered exact Korean names."""

    accepted_ids = {item.casefold() for item in account_ids}
    id_matches: list[tuple[int, str]] = []
    for row in rows:
        if not _row_matches_period(row, mapping):
            continue
        if str(row.get("account_id", "")).strip().casefold() not in accepted_ids:
            continue
        receipt = str(row.get("rcept_no", "")).strip()
        base._receipt_date(receipt)
        id_matches.append((_integral_krw(row.get("thstrm_amount"), label), receipt))
    unique_ids = tuple(dict.fromkeys(id_matches))
    if len(unique_ids) == 1:
        amount, receipt = unique_ids[0]
        return amount, receipt, "registered_account_id"
    if len(unique_ids) > 1:
        raise ValueError(
            f"PIT replay company account-id selection is ambiguous: "
            f"{mapping.source_period} {label} count={len(unique_ids)}"
        )

    allowed_names = {_norm(item) for item in _ACCOUNT_NAMES[label]}
    name_matches: list[tuple[int, str, str]] = []
    for row in rows:
        if not _row_matches_period(row, mapping):
            continue
        account_name = str(row.get("account_nm", "")).strip()
        if _norm(account_name) not in allowed_names:
            continue
        receipt = str(row.get("rcept_no", "")).strip()
        base._receipt_date(receipt)
        name_matches.append(
            (
                _integral_krw(row.get("thstrm_amount"), label),
                receipt,
                _norm(account_name),
            )
        )
    semantic = tuple(dict.fromkeys(name_matches))
    if len(semantic) != 1:
        observed = tuple(
            sorted(
                {
                    str(row.get("account_nm", "")).strip()
                    for row in rows
                    if _row_matches_period(row, mapping)
                    and _norm(row.get("account_nm", "")) in allowed_names
                }
            )
        )
        raise ValueError(
            f"PIT replay company exact-name account must resolve uniquely: "
            f"{mapping.source_period} {label} count={len(semantic)} names={observed}"
        )
    amount, receipt, _name = semantic[0]
    return amount, receipt, "exact_account_name"


@dataclass(frozen=True)
class _ReplayCompanyCapture:
    rcept_no: str
    receipt_date: date
    revenue_krw: int
    gross_profit_krw: int
    raw_payload_sha256: str
    raw_path: Path
    raw_bytes_sha256: str
    account_selection_basis: tuple[tuple[str, str], ...]


def _capture_company_source_for_replay(
    client: OpenDartReadOnlyClient,
    mapping: base.PITPanelExpansionMapping,
    *,
    evaluation_date: date,
    output: Path,
) -> _ReplayCompanyCapture:
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
    revenue, revenue_receipt, revenue_basis = select_company_account_for_replay(
        rows,
        template.revenue_account_ids,
        mapping,
        label="revenue",
    )
    cost, cost_receipt, cost_basis = select_company_account_for_replay(
        rows,
        template.cost_of_sales_account_ids,
        mapping,
        label="cost_of_sales",
    )
    gross, gross_receipt, gross_basis = select_company_account_for_replay(
        rows,
        template.gross_profit_account_ids,
        mapping,
        label="gross_profit",
    )
    receipts = {revenue_receipt, cost_receipt, gross_receipt}
    if len(receipts) != 1:
        raise ValueError("PIT replay company accounts cross filing receipts")
    receipt = next(iter(receipts))
    receipt_date = base._receipt_date(receipt)
    if mapping.expected_receipt is not None and receipt != mapping.expected_receipt:
        raise ValueError(
            f"PIT replay company receipt does not match frozen receipt: "
            f"{mapping.source_period} actual={receipt} expected={mapping.expected_receipt}"
        )
    if receipt_date > evaluation_date:
        raise ValueError("PIT replay company source is future-dated")
    if revenue - cost != gross:
        raise ValueError(
            f"PIT replay company accounting identity failed: {mapping.source_period}"
        )

    period_root = output / mapping.source_period
    period_root.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(UTC)
    stamp = captured_at.strftime("%Y%m%dT%H%M%S%fZ")
    raw_path = period_root / f"{stamp}__raw_payload.json"
    raw_bytes = json.dumps(
        raw_payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    raw_path.write_bytes(raw_bytes)
    selection_path = period_root / f"{stamp}__account_selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "source_period": mapping.source_period,
                "rcept_no": receipt,
                "selection_basis": {
                    "revenue": revenue_basis,
                    "cost_of_sales": cost_basis,
                    "gross_profit": gross_basis,
                },
                "exact_name_fallback_registry": {
                    key: sorted(values) for key, values in _ACCOUNT_NAMES.items()
                },
                "target_value_read": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return _ReplayCompanyCapture(
        rcept_no=receipt,
        receipt_date=receipt_date,
        revenue_krw=revenue,
        gross_profit_krw=gross,
        raw_payload_sha256=_sha(raw_payload),
        raw_path=raw_path,
        raw_bytes_sha256=_sha_bytes(raw_bytes),
        account_selection_basis=(
            ("revenue", revenue_basis),
            ("cost_of_sales", cost_basis),
            ("gross_profit", gross_basis),
        ),
    )


def _certification_dict(
    certification: OpenDartPeriodicProductRevenueCertification,
) -> dict[str, object]:
    payload = asdict(certification)
    for key in ("evaluation_date", "receipt_date", "period_start", "period_end"):
        payload[key] = getattr(certification, key).isoformat()
    return payload


def _write_replay_failure(
    root: Path,
    *,
    archive: DisclosureDocumentArchive,
    rcept_no: str,
    report_name: str,
    receipt_date: date,
    error: Exception,
    captured_at: datetime,
) -> Path:
    directory = (
        root
        / "failed"
        / (
            captured_at.strftime("%Y%m%dT%H%M%S%fZ")
            + "__"
            + rcept_no
        )
    )
    directory.mkdir(parents=True, exist_ok=False)
    archive_path = directory / "opendart_document.zip"
    text_path = directory / "normalized_document.txt"
    archive_path.write_bytes(archive.archive_bytes)
    text_path.write_text(archive.evidence.text, encoding="utf-8")
    diagnostic_path = directory / "diagnostic.json"
    diagnostic_path.write_text(
        json.dumps(
            {
                "status": "skhynix_ex_ante_pit_immutable_receipt_replay_failed",
                "captured_at": captured_at.isoformat(),
                "rcept_no": rcept_no,
                "report_name": report_name,
                "receipt_date": receipt_date.isoformat(),
                "retrieved_at": archive.evidence.retrieved_at.isoformat(),
                "archive_path": str(archive_path),
                "archive_sha256": archive.evidence.archive_sha256,
                "text_path": str(text_path),
                "text_sha256": archive.evidence.text_sha256,
                "error_type": type(error).__name__,
                "error": str(error),
                "target_value_read": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return diagnostic_path


def _capture_product_source_for_replay(
    client: OpenDartReadOnlyClient,
    spec: PeriodicProductRevenueSpec,
    mapping: base.PITPanelExpansionMapping,
    *,
    evaluation_date: date,
    output: Path,
) -> tuple[OpenDartPeriodicProductRevenueCertification, Path]:
    captured_at = datetime.now(UTC)
    output.mkdir(parents=True, exist_ok=True)
    discovery = discover_periodic_product_revenue(client, spec)
    if mapping.expected_receipt is not None and discovery.rcept_no != mapping.expected_receipt:
        raise ValueError(
            f"PIT replay product receipt does not match frozen receipt: "
            f"{mapping.source_period} actual={discovery.rcept_no} "
            f"expected={mapping.expected_receipt}"
        )
    if discovery.receipt_date > evaluation_date:
        raise ValueError("PIT replay product filing receipt is after evaluation date")
    archive = OpenDartDisclosureDocumentClient(client).document_with_archive(
        discovery.rcept_no
    )
    document = archive.evidence
    try:
        if document.rcept_no != discovery.rcept_no:
            raise ValueError("PIT replay product receipt/document mismatch")
        if _sha_bytes(archive.archive_bytes) != document.archive_sha256:
            raise ValueError("PIT replay product raw archive hash mismatch")
        if document.text_truncated:
            raise ValueError("PIT replay product normalized text is truncated")
        product_metrics = parse_periodic_product_revenue_source_consensus(
            spec=spec,
            text=document.text,
            archive_bytes=archive.archive_bytes,
        )
        payload = _payload(
            discovery,
            document,
            product_metrics,
            evaluation_date=evaluation_date,
        )
        evidence_id = _sha(payload)
        certification = OpenDartPeriodicProductRevenueCertification(
            evidence_id=evidence_id,
            evaluation_date=evaluation_date,
            document_id=spec.document_id,
            ticker=spec.ticker,
            issuer_name=spec.issuer_name,
            rcept_no=discovery.rcept_no,
            report_name=discovery.report_name,
            receipt_date=discovery.receipt_date,
            period_start=spec.period_start,
            period_end=spec.period_end,
            metrics=product_metrics,
            archive_sha256=document.archive_sha256,
            archive_bytes=document.archive_bytes,
            text_sha256=document.text_sha256,
            text_chars=document.text_chars,
            source_url=(
                "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + discovery.rcept_no
            ),
        )
    except Exception as exc:
        diagnostic = _write_replay_failure(
            output,
            archive=archive,
            rcept_no=discovery.rcept_no,
            report_name=discovery.report_name,
            receipt_date=discovery.receipt_date,
            error=exc,
            captured_at=captured_at,
        )
        raise ValueError(
            f"{exc}; immutable-receipt replay diagnostic preserved at {diagnostic}"
        ) from exc

    directory = output / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + certification.evidence_id[:12]
    )
    temporary = output / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("PIT replay product artifact path already exists")
    temporary.mkdir()
    try:
        archive_path = temporary / "opendart_document.zip"
        text_path = temporary / "normalized_document.txt"
        certification_path = temporary / "certification.json"
        archive_path.write_bytes(archive.archive_bytes)
        text_bytes = document.text.encode("utf-8")
        if _sha_bytes(text_bytes) != document.text_sha256:
            raise ValueError("PIT replay normalized text in-memory hash mismatch")
        text_path.write_bytes(text_bytes)
        certification_path.write_text(
            json.dumps(
                _certification_dict(certification),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    archive_path = directory / "opendart_document.zip"
    pointer_path = output / "latest_certification.json"
    temporary_pointer = output / ".latest_certification.json.tmp"
    pointer = {
        "status": "skhynix_opendart_q2_product_revenue_certified",
        "evidence_id": certification.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "certification_path": str(directory / "certification.json"),
        "archive_path": str(archive_path),
        "archive_sha256": certification.archive_sha256,
        "normalized_text_path": str(directory / "normalized_document.txt"),
        "text_sha256": certification.text_sha256,
        "rcept_no": certification.rcept_no,
        "report_name": certification.report_name,
        "source_url": certification.source_url,
        "immutable_receipt_replay": True,
        "retrieved_at": document.retrieved_at.isoformat(),
        "retrieval_after_evaluation_date": (
            document.retrieved_at.date() > evaluation_date
        ),
        "target_value_read": False,
        "product_revenue_baseline_eligible": True,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    bind_periodic_product_revenue_parser_contract(pointer_path, spec)
    verified = load_periodic_product_revenue_certification(
        pointer_path,
        evaluation_date=evaluation_date,
    )
    if verified.evidence_id != certification.evidence_id:
        raise ValueError("PIT replay product evidence drifted after parser-contract binding")
    return verified, archive_path


def _acquire_source_record_for_replay(
    client: OpenDartReadOnlyClient,
    contract: base.FrozenPITPanelExpansionContract,
    protocol: FrozenCompanyGPExAnteProtocol,
    mapping: base.PITPanelExpansionMapping,
    *,
    evaluation_date: date,
    company_output: Path,
    product_output: Path,
    template_registry: str | Path,
) -> tuple[LaggedFilingSourceRecord, base.ExpansionSourceAttempt]:
    company = _capture_company_source_for_replay(
        client,
        mapping,
        evaluation_date=evaluation_date,
        output=company_output,
    )
    if base._source_available_at(company.receipt_date) > protocol.origin_for(
        mapping.target_period
    ):
        raise ValueError(
            f"PIT replay company source misses target forecast origin: "
            f"{mapping.source_period}->{mapping.target_period}"
        )
    spec = base.build_expansion_product_spec(
        contract,
        mapping,
        template_registry=template_registry,
    )
    product, archive_path = _capture_product_source_for_replay(
        client,
        spec,
        mapping,
        evaluation_date=evaluation_date,
        output=product_output / mapping.source_period,
    )
    if product.rcept_no != company.rcept_no:
        raise ValueError(
            f"PIT replay company/product receipt mismatch: {mapping.source_period}"
        )
    if product.receipt_date != company.receipt_date:
        raise ValueError(
            f"PIT replay company/product receipt-date mismatch: {mapping.source_period}"
        )
    if _sha_bytes(archive_path.read_bytes()) != product.archive_sha256:
        raise ValueError(f"PIT replay product archive hash mismatch: {mapping.source_period}")
    gap_krw = abs(
        company.revenue_krw
        - int(round(float(product.metrics.reported_company_revenue) * 1_000_000.0))
    )
    if gap_krw > contract.company_product_reconciliation_tolerance_krw:
        raise ValueError(
            f"PIT replay company/product revenue reconciliation failed: "
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
    attempt = base.ExpansionSourceAttempt(
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


def _attempt_mapping_for_replay(
    client: OpenDartReadOnlyClient,
    contract: base.FrozenPITPanelExpansionContract,
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
    mapping: base.PITPanelExpansionMapping,
    *,
    evaluation_date: date,
    company_output: Path,
    product_output: Path,
    template_registry: str | Path,
) -> tuple[base.ExpansionSourceAttempt, LaggedFilingPeriodCertification | None]:
    try:
        record, attempt = _acquire_source_record_for_replay(
            client,
            contract,
            protocol,
            mapping,
            evaluation_date=evaluation_date,
            company_output=company_output,
            product_output=product_output,
            template_registry=template_registry,
        )
        certification = base.certify_expansion_source_record(protocol, frontier, record)
        return attempt, certification
    except Exception as exc:
        return (
            base.ExpansionSourceAttempt(
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


def run_target_blind_pit_panel_expansion_replay(
    client: OpenDartReadOnlyClient,
    *,
    evaluation_date: date,
    manifest: str | Path = base.DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION,
    base_bundle_path: str | Path = DEFAULT_LAGGED_FILING_BUNDLE,
    protocol_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    feature_frontier_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER,
    estimator_freeze_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    base_certification_contract_path: str | Path = DEFAULT_LAGGED_FILING_CERTIFICATION,
    company_output: str | Path = _DEFAULT_COMPANY_OUTPUT,
    product_output: str | Path = _DEFAULT_PRODUCT_OUTPUT,
    product_template_registry: str | Path = DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
    combined_bundle_output: str | Path = base.DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
    report_output: str | Path = base.DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT,
    created_at: datetime | None = None,
) -> base.ExpansionRunResult:
    """Run the unchanged expansion selection with corrected immutable-source replay mechanics."""

    contract = base.load_frozen_pit_panel_expansion_contract(manifest)
    protocol = load_frozen_company_gp_ex_ante_protocol(protocol_path)
    frontier = load_ex_ante_feature_frontier(feature_frontier_path)
    estimator_freeze = load_frozen_ex_ante_estimator_selection(estimator_freeze_path)
    base_certification = load_lagged_filing_certification_contract(
        base_certification_contract_path
    )
    if estimator_freeze.evidence_id != contract.estimator_freeze_evidence_id:
        raise ValueError("PIT replay estimator-freeze binding drifted")
    if base_certification.evidence_id != contract.base_certification_contract_evidence_id:
        raise ValueError("PIT replay base-certification binding drifted")
    base_bundle = load_point_in_time_feature_bundle(base_bundle_path)
    base_periods = base._validate_base_bundle(contract, base_bundle)

    attempts: list[base.ExpansionSourceAttempt] = []
    certifications: dict[str, LaggedFilingPeriodCertification] = {}
    for mapping in contract.fixed_mappings:
        attempt, certification = _attempt_mapping_for_replay(
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
        pair_attempts: list[base.ExpansionSourceAttempt] = []
        pair_certifications: list[LaggedFilingPeriodCertification] = []
        for mapping in pair:
            attempt, certification = _attempt_mapping_for_replay(
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

    selected_by_attempts = base.select_first_complete_legacy_year(
        contract,
        tuple(attempts),
    )
    if selected_by_attempts != selected_legacy_year:
        raise ValueError("PIT replay legacy-year selection replay drifted")

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
        combined_bundle = base._compose_bundle(
            base_bundle,
            additions,
            created_at=created_at or datetime.now(UTC),
        )
        if len(combined_bundle.observations) != contract.required_total_observations:
            raise ValueError("PIT replay combined bundle observation count drifted")
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
    result = base.ExpansionRunResult(
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
    base._persist_report(result, Path(report_output))
    return result


__all__ = [
    "DEFAULT_EX_ANTE_PIT_PANEL_REPLAY_OUTPUT",
    "run_target_blind_pit_panel_expansion_replay",
    "select_company_account_for_replay",
]
