"""Certify current-quarter SK hynix product revenue from an official OpenDART periodic filing.

This stage is deliberately stricter than a chart-share allocation:
- it exact-discovers the half-year filing instead of trusting a receipt number;
- it archives the exact OpenDART ZIP bytes;
- it accepts only a table whose current-period 3-month column is explicitly identified;
- DRAM, NAND, Other, and Total must all be directly reported in the same table;
- it never infers Other as a remainder;
- the reported product total must reconcile to the sum of the three direct rows.

The resulting revenue facts can close revenue-only model gaps. They do not certify
product profitability, a forward model, fair value, a target price, or a decision score.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.providers.opendart import CorpCode, OpenDartReadOnlyClient
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentArchive,
    DisclosureDocumentEvidence,
    OpenDartDisclosureDocumentClient,
)

DEFAULT_PERIODIC_PRODUCT_REVENUE_REGISTRY = Path(
    "config/semiconductor_periodic_product_revenue.yaml"
)
DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT = Path(
    "data/private/research/skhynix-opendart-q2-product-revenue-certification"
)
DEFAULT_PERIODIC_PRODUCT_REVENUE_POINTER = (
    DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT / "latest_certification.json"
)
_AMOUNT_TOKEN = re.compile(r"^-?\(?[0-9][0-9,]*(?:\.[0-9]+)?\)?$")
_ALLOWED_UNIT_MARKERS = {"백만원": ("KRW_million", 1.0), "억원": ("KRW_million", 100.0)}
_REQUIRED_BLOCKS = (
    "dram_total",
    "nand_and_solutions",
    "other_products_services",
    "reported_company_revenue",
)


@dataclass(frozen=True)
class PeriodicProductRevenueSpec:
    document_id: str
    ticker: str
    issuer_name: str
    source_id: str
    report_name_exact: str
    discovery_begin_date: date
    discovery_end_date: date
    period_start: date
    period_end: date
    parser_id: str
    expected_identity_anchors: tuple[str, ...]
    product_labels: dict[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Periodic product revenue ticker must be six digits")
        if self.source_id != "opendart":
            raise ValueError("Periodic product revenue requires official OpenDART")
        if self.discovery_begin_date > self.discovery_end_date:
            raise ValueError("Periodic product revenue discovery window is invalid")
        if self.period_start > self.period_end:
            raise ValueError("Periodic product revenue accounting period is invalid")
        if self.period_end > self.discovery_end_date:
            raise ValueError("Periodic product revenue filing window precedes period end")
        if set(self.product_labels) != set(_REQUIRED_BLOCKS):
            raise ValueError("Periodic product revenue labels must cover all required rows")
        if not self.expected_identity_anchors:
            raise ValueError("Periodic product revenue requires identity anchors")


@dataclass(frozen=True)
class DiscoveredPeriodicProductRevenue:
    spec: PeriodicProductRevenueSpec
    corp: CorpCode
    rcept_no: str
    report_name: str
    receipt_date: date

    def __post_init__(self) -> None:
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Periodic product revenue receipt number must be 14 digits")
        if self.report_name != self.spec.report_name_exact:
            raise ValueError("Periodic product revenue report name is not exact")
        if not (
            self.spec.discovery_begin_date
            <= self.receipt_date
            <= self.spec.discovery_end_date
        ):
            raise ValueError("Periodic product revenue receipt date is outside discovery window")
        if self.corp.stock_code != self.spec.ticker:
            raise ValueError("Periodic product revenue corporation does not match ticker")


@dataclass(frozen=True)
class ProductRevenueMetrics:
    unit: str
    dram_total: float
    nand_and_solutions: float
    other_products_services: float
    reported_company_revenue: float
    direct_sum: float
    reconciliation_delta: float

    def __post_init__(self) -> None:
        if self.unit != "KRW_million":
            raise ValueError("Product revenue metrics must normalize to KRW_million")
        if min(
            self.dram_total,
            self.nand_and_solutions,
            self.other_products_services,
            self.reported_company_revenue,
        ) < 0:
            raise ValueError("Product revenue metrics cannot be negative")
        if self.reported_company_revenue <= 0:
            raise ValueError("Reported product revenue total must be positive")
        if abs(self.direct_sum - self.reported_company_revenue) > 0.5:
            raise ValueError("Direct product revenues do not reconcile to reported total")
        if abs(self.reconciliation_delta) > 0.5:
            raise ValueError("Product revenue reconciliation delta exceeds tolerance")


@dataclass(frozen=True)
class OpenDartPeriodicProductRevenueCertification:
    evidence_id: str
    evaluation_date: date
    document_id: str
    ticker: str
    issuer_name: str
    rcept_no: str
    report_name: str
    receipt_date: date
    period_start: date
    period_end: date
    metrics: ProductRevenueMetrics
    archive_sha256: str
    archive_bytes: int
    text_sha256: str
    text_chars: int
    source_url: str
    source_receipt_certified: bool = True
    source_archive_bytes_archived: bool = True
    source_vintage_certified: bool = True
    current_quarter_period_certified: bool = True
    direct_product_revenue_semantics_certified: bool = True
    other_amount_certified: bool = True
    company_revenue_reconciliation_certified: bool = True
    product_revenue_baseline_eligible: bool = True
    allocation_resolver_registered: bool = False
    product_profitability_certified: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (self.evidence_id, self.archive_sha256, self.text_sha256)
        if any(len(value) != 64 for value in hashes):
            raise ValueError("Periodic product revenue hashes must be SHA-256")
        if self.receipt_date > self.evaluation_date:
            raise ValueError("Periodic product revenue cannot use future evidence")
        required = (
            self.source_receipt_certified,
            self.source_archive_bytes_archived,
            self.source_vintage_certified,
            self.current_quarter_period_certified,
            self.direct_product_revenue_semantics_certified,
            self.other_amount_certified,
            self.company_revenue_reconciliation_certified,
            self.product_revenue_baseline_eligible,
        )
        if not all(required):
            raise ValueError("Periodic product revenue certification lost a required trust flag")
        forbidden = (
            self.allocation_resolver_registered,
            self.product_profitability_certified,
            self.numeric_forecast_enabled,
            self.fair_value_estimate_enabled,
            self.target_price_enabled,
            self.decision_score_enabled,
        )
        if any(forbidden):
            raise ValueError("Periodic product revenue exceeds its trust boundary")


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Periodic product revenue {label} must be an array")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if not result:
        raise ValueError(f"Periodic product revenue {label} cannot be empty")
    return result


def load_periodic_product_revenue_registry(
    path: str | Path = DEFAULT_PERIODIC_PRODUCT_REVENUE_REGISTRY,
) -> dict[str, PeriodicProductRevenueSpec]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("issuers"), dict):
        raise ValueError("Periodic product revenue registry must contain issuers")
    specs: dict[str, PeriodicProductRevenueSpec] = {}
    for ticker_raw, issuer_value in cast(dict[object, object], payload["issuers"]).items():
        ticker = str(ticker_raw).strip().zfill(6)
        if not isinstance(issuer_value, dict):
            raise ValueError(f"Periodic product revenue issuer must be an object: {ticker}")
        issuer = cast(dict[object, object], issuer_value)
        issuer_name = str(issuer.get("issuer_name", "")).strip()
        disclosures = issuer.get("disclosures")
        if not isinstance(disclosures, dict):
            raise ValueError(f"Periodic product revenue disclosures must be an object: {ticker}")
        for raw_id, raw_value in cast(dict[object, object], disclosures).items():
            if not isinstance(raw_value, dict):
                raise ValueError("Periodic product revenue disclosure must be an object")
            raw = cast(dict[object, object], raw_value)
            labels_raw = raw.get("product_labels")
            if not isinstance(labels_raw, dict):
                raise ValueError("Periodic product revenue product_labels must be an object")
            labels = {
                str(key): _strings(value, f"product_labels.{key}")
                for key, value in cast(dict[object, object], labels_raw).items()
            }
            document_id = str(raw_id).strip()
            spec = PeriodicProductRevenueSpec(
                document_id=document_id,
                ticker=ticker,
                issuer_name=issuer_name,
                source_id=str(raw.get("source_id", "")).strip(),
                report_name_exact=str(raw.get("report_name_exact", "")).strip(),
                discovery_begin_date=date.fromisoformat(
                    str(raw.get("discovery_begin_date", ""))
                ),
                discovery_end_date=date.fromisoformat(str(raw.get("discovery_end_date", ""))),
                period_start=date.fromisoformat(str(raw.get("period_start", ""))),
                period_end=date.fromisoformat(str(raw.get("period_end", ""))),
                parser_id=str(raw.get("parser_id", "")).strip(),
                expected_identity_anchors=_strings(
                    raw.get("expected_identity_anchors", []),
                    "expected_identity_anchors",
                ),
                product_labels=labels,
            )
            if document_id in specs:
                raise ValueError(f"Periodic product revenue document duplicated: {document_id}")
            specs[document_id] = spec
    if not specs:
        raise ValueError("Periodic product revenue registry is empty")
    return specs


def discover_periodic_product_revenue(
    client: OpenDartReadOnlyClient,
    spec: PeriodicProductRevenueSpec,
) -> DiscoveredPeriodicProductRevenue:
    corp = client.resolve_stock_codes([spec.ticker])[spec.ticker]
    batch = client.disclosures(
        corp,
        begin_date=spec.discovery_begin_date,
        end_date=spec.discovery_end_date,
    )
    frame = batch.frame
    if frame.empty:
        raise ValueError("OpenDART half-year periodic filing was not found")
    exact = frame.loc[
        frame["report_name"].astype(str).eq(spec.report_name_exact)
        & frame["receipt_date"].between(
            spec.discovery_begin_date,
            spec.discovery_end_date,
            inclusive="both",
        )
        & ~frame["is_correction"].astype(bool)
    ].copy()
    if len(exact) != 1:
        receipts = (
            ",".join(exact["rcept_no"].astype(str).tolist()) if not exact.empty else "none"
        )
        raise ValueError(
            "OpenDART half-year exact disclosure match must be unique: "
            f"count={len(exact)} receipts={receipts}"
        )
    row = exact.iloc[0]
    return DiscoveredPeriodicProductRevenue(
        spec=spec,
        corp=corp,
        rcept_no=str(row["rcept_no"]),
        report_name=str(row["report_name"]),
        receipt_date=cast(date, row["receipt_date"]),
    )


def _normalize_lines(text: str) -> tuple[str, ...]:
    return tuple(
        " ".join(line.replace("\u00a0", " ").split())
        for line in text.splitlines()
        if line.strip()
    )


def _parse_amount(value: str) -> float | None:
    token = value.replace(" ", "").strip()
    if not _AMOUNT_TOKEN.fullmatch(token):
        return None
    negative = token.startswith("(") and token.endswith(")")
    token = token.strip("()").replace(",", "")
    if token.startswith("-"):
        negative = True
        token = token[1:]
    number = float(token)
    return -number if negative else number


def _unit(lines: tuple[str, ...]) -> tuple[str, float]:
    for line in lines:
        if "단위" not in line:
            continue
        for marker, normalized in _ALLOWED_UNIT_MARKERS.items():
            if marker in line:
                return normalized
    raise ValueError("OpenDART product revenue table lacks an allowed KRW unit")


def _label_index(
    lines: tuple[str, ...],
    labels: tuple[str, ...],
    *,
    start: int,
) -> int:
    normalized = {" ".join(label.split()).casefold() for label in labels}
    matches = [
        index
        for index in range(start, len(lines))
        if " ".join(lines[index].split()).casefold() in normalized
    ]
    if not matches:
        raise ValueError(f"OpenDART product revenue row missing: {labels[0]}")
    return matches[0]


def _row_first_amount(
    lines: tuple[str, ...],
    *,
    row_index: int,
    next_row_index: int,
    label: str,
) -> float:
    values = [
        amount
        for token in lines[row_index + 1 : next_row_index]
        if (amount := _parse_amount(token)) is not None
    ]
    if not values:
        raise ValueError(f"OpenDART product revenue row has no amount: {label}")
    return values[0]


def _candidate_windows(lines: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    windows: list[tuple[str, ...]] = []
    dram_indices = [index for index, line in enumerate(lines) if line.casefold() == "dram"]
    for index in dram_indices:
        start = max(0, index - 80)
        end = min(len(lines), index + 140)
        window = lines[start:end]
        joined = "\n".join(window).casefold()
        if (
            "nand" in joined
            and "3개월" in joined
            and "누적" in joined
            and ("백만원" in joined or "억원" in joined)
        ):
            windows.append(window)
    return tuple(windows)


def parse_periodic_product_revenue_text(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> ProductRevenueMetrics:
    if spec.parser_id != "skhynix_opendart_half_year_product_revenue_2026q2_v1":
        raise ValueError("Unsupported periodic product revenue parser_id")
    lines = _normalize_lines(text)
    if not lines:
        raise ValueError("OpenDART periodic document text is empty")
    folded = "\n".join(lines).casefold()
    for anchor in spec.expected_identity_anchors:
        if " ".join(anchor.split()).casefold() not in folded:
            raise ValueError(f"OpenDART periodic product revenue anchor missing: {anchor}")

    parsed: list[ProductRevenueMetrics] = []
    for window in _candidate_windows(lines):
        try:
            unit, scale = _unit(window)
            first_product = _label_index(window, spec.product_labels["dram_total"], start=0)
            header = window[:first_product]
            three_month_positions = [
                index for index, line in enumerate(header) if "3개월" in line
            ]
            cumulative_positions = [
                index for index, line in enumerate(header) if "누적" in line
            ]
            if not three_month_positions or not cumulative_positions:
                continue
            if min(three_month_positions) > min(cumulative_positions):
                continue

            dram_index = first_product
            nand_index = _label_index(
                window,
                spec.product_labels["nand_and_solutions"],
                start=dram_index + 1,
            )
            other_index = _label_index(
                window,
                spec.product_labels["other_products_services"],
                start=nand_index + 1,
            )
            total_index = _label_index(
                window,
                spec.product_labels["reported_company_revenue"],
                start=other_index + 1,
            )
            if not (dram_index < nand_index < other_index < total_index):
                continue
            end = min(len(window), total_index + 12)
            dram = _row_first_amount(
                window,
                row_index=dram_index,
                next_row_index=nand_index,
                label="DRAM",
            )
            nand = _row_first_amount(
                window,
                row_index=nand_index,
                next_row_index=other_index,
                label="NAND",
            )
            other = _row_first_amount(
                window,
                row_index=other_index,
                next_row_index=total_index,
                label="Other",
            )
            total = _row_first_amount(
                window,
                row_index=total_index,
                next_row_index=end,
                label="Total",
            )
            dram *= scale
            nand *= scale
            other *= scale
            total *= scale
            direct_sum = dram + nand + other
            parsed.append(
                ProductRevenueMetrics(
                    unit=unit,
                    dram_total=dram,
                    nand_and_solutions=nand,
                    other_products_services=other,
                    reported_company_revenue=total,
                    direct_sum=direct_sum,
                    reconciliation_delta=direct_sum - total,
                )
            )
        except ValueError:
            continue
    unique = {
        (
            item.unit,
            item.dram_total,
            item.nand_and_solutions,
            item.other_products_services,
            item.reported_company_revenue,
        ): item
        for item in parsed
    }
    if len(unique) != 1:
        raise ValueError(
            "OpenDART current-quarter product revenue table must resolve uniquely: "
            f"candidates={len(unique)}"
        )
    return next(iter(unique.values()))


def _source_url(rcept_no: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def _payload(
    discovery: DiscoveredPeriodicProductRevenue,
    document: DisclosureDocumentEvidence,
    metrics: ProductRevenueMetrics,
    *,
    evaluation_date: date,
) -> dict[str, object]:
    return {
        "evaluation_date": evaluation_date.isoformat(),
        "document_id": discovery.spec.document_id,
        "ticker": discovery.spec.ticker,
        "issuer_name": discovery.spec.issuer_name,
        "rcept_no": discovery.rcept_no,
        "report_name": discovery.report_name,
        "receipt_date": discovery.receipt_date.isoformat(),
        "period_start": discovery.spec.period_start.isoformat(),
        "period_end": discovery.spec.period_end.isoformat(),
        "metrics": asdict(metrics),
        "archive_sha256": document.archive_sha256,
        "archive_bytes": document.archive_bytes,
        "text_sha256": document.text_sha256,
        "text_chars": document.text_chars,
        "source_url": _source_url(discovery.rcept_no),
        "source_receipt_certified": True,
        "source_archive_bytes_archived": True,
        "source_vintage_certified": True,
        "current_quarter_period_certified": True,
        "direct_product_revenue_semantics_certified": True,
        "other_amount_certified": True,
        "company_revenue_reconciliation_certified": True,
        "product_revenue_baseline_eligible": True,
        "allocation_resolver_registered": False,
        "product_profitability_certified": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }


def build_periodic_product_revenue_certification(
    discovery: DiscoveredPeriodicProductRevenue,
    archive: DisclosureDocumentArchive,
    *,
    evaluation_date: date,
) -> OpenDartPeriodicProductRevenueCertification:
    document = archive.evidence
    if document.rcept_no != discovery.rcept_no:
        raise ValueError("OpenDART product revenue receipt/document mismatch")
    if hashlib.sha256(archive.archive_bytes).hexdigest() != document.archive_sha256:
        raise ValueError("OpenDART product revenue raw archive hash mismatch")
    if document.text_truncated:
        raise ValueError("OpenDART product revenue refuses truncated normalized text")
    if discovery.receipt_date > evaluation_date:
        raise ValueError("OpenDART product revenue filing is not yet observable")
    if document.retrieved_at.date() > evaluation_date:
        raise ValueError("OpenDART product revenue retrieval is after evaluation date")
    metrics = parse_periodic_product_revenue_text(discovery.spec, document.text)
    payload = _payload(discovery, document, metrics, evaluation_date=evaluation_date)
    evidence_id = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return OpenDartPeriodicProductRevenueCertification(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        document_id=discovery.spec.document_id,
        ticker=discovery.spec.ticker,
        issuer_name=discovery.spec.issuer_name,
        rcept_no=discovery.rcept_no,
        report_name=discovery.report_name,
        receipt_date=discovery.receipt_date,
        period_start=discovery.spec.period_start,
        period_end=discovery.spec.period_end,
        metrics=metrics,
        archive_sha256=document.archive_sha256,
        archive_bytes=document.archive_bytes,
        text_sha256=document.text_sha256,
        text_chars=document.text_chars,
        source_url=_source_url(discovery.rcept_no),
    )


def _certification_dict(
    item: OpenDartPeriodicProductRevenueCertification,
) -> dict[str, object]:
    payload = asdict(item)
    for key in ("evaluation_date", "receipt_date", "period_start", "period_end"):
        payload[key] = getattr(item, key).isoformat()
    return payload


def collect_periodic_product_revenue(
    client: OpenDartReadOnlyClient,
    spec: PeriodicProductRevenueSpec,
    *,
    evaluation_date: date,
) -> tuple[OpenDartPeriodicProductRevenueCertification, DisclosureDocumentArchive]:
    discovery = discover_periodic_product_revenue(client, spec)
    archive = OpenDartDisclosureDocumentClient(client).document_with_archive(discovery.rcept_no)
    certification = build_periodic_product_revenue_certification(
        discovery,
        archive,
        evaluation_date=evaluation_date,
    )
    return certification, archive


def capture_periodic_product_revenue_certification(
    client: OpenDartReadOnlyClient,
    spec: PeriodicProductRevenueSpec,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    certification, archive = collect_periodic_product_revenue(
        client,
        spec,
        evaluation_date=evaluation_date,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + certification.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("Periodic product revenue artifact path already exists")
    temporary.mkdir()
    try:
        archive_path = temporary / "opendart_document.zip"
        text_path = temporary / "normalized_document.txt"
        certification_path = temporary / "certification.json"
        archive_path.write_bytes(archive.archive_bytes)
        text_path.write_text(archive.evidence.text, encoding="utf-8")
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

    pointer = {
        "status": "skhynix_opendart_q2_product_revenue_certified",
        "evidence_id": certification.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "certification_path": str(directory / "certification.json"),
        "archive_path": str(directory / "opendart_document.zip"),
        "archive_sha256": certification.archive_sha256,
        "normalized_text_path": str(directory / "normalized_document.txt"),
        "text_sha256": certification.text_sha256,
        "rcept_no": certification.rcept_no,
        "report_name": certification.report_name,
        "source_url": certification.source_url,
        "product_revenue_baseline_eligible": True,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    pointer_path = root / "latest_certification.json"
    temporary_pointer = root / ".latest_certification.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return pointer


__all__ = [
    "DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT",
    "DEFAULT_PERIODIC_PRODUCT_REVENUE_POINTER",
    "DEFAULT_PERIODIC_PRODUCT_REVENUE_REGISTRY",
    "DiscoveredPeriodicProductRevenue",
    "OpenDartPeriodicProductRevenueCertification",
    "PeriodicProductRevenueSpec",
    "ProductRevenueMetrics",
    "build_periodic_product_revenue_certification",
    "capture_periodic_product_revenue_certification",
    "collect_periodic_product_revenue",
    "discover_periodic_product_revenue",
    "load_periodic_product_revenue_registry",
    "parse_periodic_product_revenue_text",
]