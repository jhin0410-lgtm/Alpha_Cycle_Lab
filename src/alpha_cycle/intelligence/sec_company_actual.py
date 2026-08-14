"""Source-bounded SK hynix company-level actuals from official SEC EDGAR filings.

This layer independently corroborates company totals already available from OpenDART.
It does not create product-level DRAM/NAND/HBM baselines.  Discovery is pinned to an
exact SEC accession and primary document, while current SEC submissions metadata is
still re-checked before bytes are accepted.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import cast
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml

DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY = Path("config/semiconductor_sec_company_actual.yaml")
SEC_SUBMISSIONS_ROOT = "https://data.sec.gov/submissions"
SEC_ARCHIVES_ROOT = "https://www.sec.gov/Archives/edgar/data"
_ALLOWED_SEC_HOSTS = frozenset({"data.sec.gov", "www.sec.gov"})
_AMOUNT = re.compile(r"^-?[0-9][0-9,]*(?:\.[0-9]+)?$")
_METRIC_LABELS = (
    "Revenue",
    "Operating Profit (Loss)",
    "Profit (Loss) from Continuing Operations Before Income Tax",
    "Profit (Loss) for the Period",
    "Attributable To: Controlling Interests",
)
_METRIC_LABELS_CASEFOLD = frozenset(item.casefold() for item in _METRIC_LABELS)


@dataclass(frozen=True)
class SecCompanyActualSpec:
    document_id: str
    ticker: str
    issuer_name: str
    source_id: str
    cik: str
    form: str
    filing_date: date
    expected_accession_number: str
    expected_primary_document: str
    period_start: date
    period_end: date
    parser_id: str
    company_level_actual: bool
    provisional: bool
    audited: bool
    product_baseline_eligible: bool
    required_identity_anchors: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("SEC company actual ticker must be six digits")
        if self.source_id != "sec_edgar" or self.form != "6-K":
            raise ValueError("SEC company actual v1 requires an official SEC 6-K")
        if len(self.cik) != 10 or not self.cik.isdigit():
            raise ValueError("SEC company actual CIK must be ten digits")
        accession_parts = self.expected_accession_number.split("-")
        if (
            len(accession_parts) != 3
            or tuple(len(item) for item in accession_parts) != (10, 2, 6)
            or not all(item.isdigit() for item in accession_parts)
        ):
            raise ValueError("SEC company actual accession number is invalid")
        if not self.expected_primary_document.endswith((".htm", ".html")):
            raise ValueError("SEC company actual primary document must be HTML")
        if self.period_start > self.period_end or self.period_end > self.filing_date:
            raise ValueError("SEC company actual accounting/filing dates are invalid")
        if (
            not self.company_level_actual
            or not self.provisional
            or self.audited
            or self.product_baseline_eligible
        ):
            raise ValueError("SEC company actual v1 must remain provisional company-only evidence")
        if not self.required_identity_anchors:
            raise ValueError("SEC company actual requires identity anchors")

    @property
    def submissions_url(self) -> str:
        return f"{SEC_SUBMISSIONS_ROOT}/CIK{self.cik}.json"

    @property
    def filing_url(self) -> str:
        accession = self.expected_accession_number.replace("-", "")
        cik_numeric = str(int(self.cik))
        return (
            f"{SEC_ARCHIVES_ROOT}/{cik_numeric}/{accession}/"
            f"{self.expected_primary_document}"
        )


@dataclass(frozen=True)
class SecDiscoveredFiling:
    spec: SecCompanyActualSpec
    accession_number: str
    primary_document: str
    filing_date: date

    def __post_init__(self) -> None:
        if self.accession_number != self.spec.expected_accession_number:
            raise ValueError("SEC discovered accession does not match the pinned registry")
        if self.primary_document != self.spec.expected_primary_document:
            raise ValueError("SEC discovered primary document does not match the pinned registry")
        if self.filing_date != self.spec.filing_date:
            raise ValueError("SEC discovered filing date does not match the pinned registry")


@dataclass(frozen=True)
class SecCompanyActualMetrics:
    unit: str
    revenue: float
    operating_income: float
    net_income: float

    def __post_init__(self) -> None:
        if self.unit != "KRW_million":
            raise ValueError("SEC company actual v1 normalizes to KRW_million")
        if self.revenue <= 0:
            raise ValueError("SEC company actual revenue must be positive")


@dataclass(frozen=True)
class SecCompanyActualEvidence:
    evidence_id: str
    evaluation_date: date
    document_id: str
    ticker: str
    issuer_name: str
    accession_number: str
    primary_document: str
    filing_date: date
    period_start: date
    period_end: date
    submissions_url: str
    filing_url: str
    submissions_sha256: str
    filing_sha256: str
    metrics: SecCompanyActualMetrics
    company_level_actual: bool = True
    provisional: bool = True
    audited: bool = False
    product_baseline_eligible: bool = False
    source_bytes_archived: bool = True
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (self.evidence_id, self.submissions_sha256, self.filing_sha256)
        if any(len(item) != 64 for item in hashes):
            raise ValueError("SEC company actual evidence hashes must be SHA-256")
        if self.filing_date > self.evaluation_date or self.period_end > self.evaluation_date:
            raise ValueError("SEC company actual cannot use future evidence")
        if not self.company_level_actual or not self.provisional or not self.source_bytes_archived:
            raise ValueError("SEC company actual required evidence flags are invalid")
        if (
            self.audited
            or self.product_baseline_eligible
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SEC company actual evidence exceeds its trust boundary")
        for url in (self.submissions_url, self.filing_url):
            host = (urlparse(url).hostname or "").casefold()
            if host not in _ALLOWED_SEC_HOSTS:
                raise ValueError("SEC company actual evidence points outside official SEC hosts")


class _VisibleTextParser(HTMLParser):
    _IGNORED = frozenset({"script", "style", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() in self._IGNORED:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self._IGNORED and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0 and data.strip():
            self.parts.append(data)


def _strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"SEC company actual {label} must be boolean")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"SEC company actual {label} must be an array")
    items = tuple(str(item).strip() for item in value if str(item).strip())
    if not items:
        raise ValueError(f"SEC company actual {label} cannot be empty")
    return items


def load_sec_company_actual_registry(
    path: str | Path = DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY,
) -> dict[str, SecCompanyActualSpec]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("issuers"), dict):
        raise ValueError("SEC company actual registry must contain issuers")
    result: dict[str, SecCompanyActualSpec] = {}
    for raw_ticker, raw_issuer in cast(dict[object, object], payload["issuers"]).items():
        ticker = str(raw_ticker).strip().zfill(6)
        if not isinstance(raw_issuer, dict):
            raise ValueError(f"SEC company actual issuer must be an object: {ticker}")
        issuer = cast(dict[object, object], raw_issuer)
        filings = issuer.get("filings", {})
        if not isinstance(filings, dict):
            raise ValueError(f"SEC company actual filings must be an object: {ticker}")
        for raw_id, raw_value in cast(dict[object, object], filings).items():
            document_id = str(raw_id).strip()
            if not isinstance(raw_value, dict):
                raise ValueError(f"SEC company actual filing must be an object: {document_id}")
            raw = cast(dict[object, object], raw_value)
            spec = SecCompanyActualSpec(
                document_id=document_id,
                ticker=ticker,
                issuer_name=str(issuer.get("issuer_name", "")).strip(),
                source_id=str(raw.get("source_id", "")).strip(),
                cik=str(raw.get("cik", "")).strip().zfill(10),
                form=str(raw.get("form", "")).strip(),
                filing_date=date.fromisoformat(str(raw.get("filing_date", ""))),
                expected_accession_number=str(raw.get("expected_accession_number", "")).strip(),
                expected_primary_document=str(raw.get("expected_primary_document", "")).strip(),
                period_start=date.fromisoformat(str(raw.get("period_start", ""))),
                period_end=date.fromisoformat(str(raw.get("period_end", ""))),
                parser_id=str(raw.get("parser_id", "")).strip(),
                company_level_actual=_strict_bool(
                    raw.get("company_level_actual"), "company_level_actual"
                ),
                provisional=_strict_bool(raw.get("provisional"), "provisional"),
                audited=_strict_bool(raw.get("audited"), "audited"),
                product_baseline_eligible=_strict_bool(
                    raw.get("product_baseline_eligible"), "product_baseline_eligible"
                ),
                required_identity_anchors=_string_tuple(
                    raw.get("required_identity_anchors", []), "required_identity_anchors"
                ),
            )
            if document_id in result:
                raise ValueError(f"SEC company actual filing is duplicated: {document_id}")
            result[document_id] = spec
    if not result:
        raise ValueError("SEC company actual registry is empty")
    return result


def validate_sec_user_agent(value: str) -> str:
    user_agent = " ".join(value.split())
    if not user_agent or "@" not in user_agent or len(user_agent) < 8:
        raise ValueError(
            "SEC_EDGAR_USER_AGENT must declare an application/company name and contact email"
        )
    return user_agent


def download_sec_bytes(url: str, *, user_agent: str, timeout_seconds: float = 20.0) -> bytes:
    host = (urlparse(url).hostname or "").casefold()
    if host not in _ALLOWED_SEC_HOSTS:
        raise ValueError("SEC download URL must remain on an official SEC host")
    if timeout_seconds <= 0:
        raise ValueError("SEC timeout_seconds must be positive")
    declared = validate_sec_user_agent(user_agent)
    request = Request(
        url,
        headers={
            "User-Agent": declared,
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.1",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return cast(bytes, response.read())


def discover_sec_company_actual(
    spec: SecCompanyActualSpec,
    submissions_bytes: bytes,
) -> SecDiscoveredFiling:
    try:
        payload: object = json.loads(submissions_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SEC submissions payload is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("SEC submissions payload must be an object")
    root = cast(dict[str, object], payload)
    filings = root.get("filings")
    if not isinstance(filings, dict):
        raise ValueError("SEC submissions payload is missing filings")
    recent = cast(dict[str, object], filings).get("recent")
    if not isinstance(recent, dict):
        raise ValueError("SEC submissions payload is missing recent filings")
    recent_map = cast(dict[str, object], recent)
    required = (
        "accessionNumber",
        "filingDate",
        "form",
        "primaryDocument",
    )
    columns: dict[str, list[object]] = {}
    for key in required:
        raw = recent_map.get(key)
        if not isinstance(raw, list):
            raise ValueError(f"SEC submissions recent.{key} must be an array")
        columns[key] = raw
    lengths = {len(items) for items in columns.values()}
    if len(lengths) != 1:
        raise ValueError("SEC submissions recent filing arrays are misaligned")

    matches: list[SecDiscoveredFiling] = []
    for index in range(next(iter(lengths), 0)):
        accession = str(columns["accessionNumber"][index]).strip()
        filing_date_raw = str(columns["filingDate"][index]).strip()
        form = str(columns["form"][index]).strip()
        primary_document = str(columns["primaryDocument"][index]).strip()
        if form != spec.form or filing_date_raw != spec.filing_date.isoformat():
            continue
        if accession != spec.expected_accession_number:
            continue
        matches.append(
            SecDiscoveredFiling(
                spec=spec,
                accession_number=accession,
                primary_document=primary_document,
                filing_date=date.fromisoformat(filing_date_raw),
            )
        )
    if len(matches) != 1:
        raise ValueError(
            "Pinned SEC company actual filing must resolve exactly once: "
            f"count={len(matches)}"
        )
    return matches[0]


def extract_sec_visible_parts(html_bytes: bytes) -> tuple[str, ...]:
    parser = _VisibleTextParser()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    parser.close()
    parts = tuple(" ".join(item.replace("\u00a0", " ").split()) for item in parser.parts)
    return tuple(item for item in parts if item)


def _require_anchor(parts: tuple[str, ...], anchor: str) -> None:
    joined = " ".join(parts).casefold()
    if " ".join(anchor.split()).casefold() not in joined:
        raise ValueError(f"SEC company actual identity anchor is missing: {anchor}")


def _amount_token(value: str) -> float | None:
    token = value.strip().replace(" ", "")
    if not _AMOUNT.fullmatch(token):
        return None
    return float(token.replace(",", ""))


def _metric_current_value(parts: tuple[str, ...], label: str) -> float:
    indices = [index for index, item in enumerate(parts) if item.casefold() == label.casefold()]
    if len(indices) != 1:
        raise ValueError(f"SEC company actual metric label must be unique: {label}")
    start = indices[0]
    section_end = next(
        (
            index
            for index in range(start + 1, len(parts))
            if parts[index].casefold() in _METRIC_LABELS_CASEFOLD
        ),
        len(parts),
    )
    section = parts[start + 1 : section_end]
    amounts = [amount for item in section if (amount := _amount_token(item)) is not None]
    if len(amounts) < 2:
        raise ValueError(f"SEC company actual metric section is incomplete: {label}")
    return amounts[0]


def parse_sec_company_actual_html(
    spec: SecCompanyActualSpec,
    html_bytes: bytes,
) -> SecCompanyActualMetrics:
    if spec.parser_id != "skhynix_sec_6k_2026q2_provisional_v1":
        raise ValueError("SEC company actual parser received an unsupported parser_id")
    parts = extract_sec_visible_parts(html_bytes)
    if not parts:
        raise ValueError("SEC company actual filing has no visible text")
    for anchor in spec.required_identity_anchors:
        _require_anchor(parts, anchor)
    joined = " ".join(parts)
    if "in millions of Won or %" not in joined:
        raise ValueError("SEC company actual filing unit anchor is missing")
    return SecCompanyActualMetrics(
        unit="KRW_million",
        revenue=_metric_current_value(parts, "Revenue"),
        operating_income=_metric_current_value(parts, "Operating Profit (Loss)"),
        net_income=_metric_current_value(parts, "Profit (Loss) for the Period"),
    )


def build_sec_company_actual_evidence(
    spec: SecCompanyActualSpec,
    *,
    evaluation_date: date,
    submissions_bytes: bytes,
    filing_bytes: bytes,
) -> SecCompanyActualEvidence:
    if spec.filing_date > evaluation_date or spec.period_end > evaluation_date:
        raise ValueError("SEC company actual filing is not observable by evaluation date")
    discovered = discover_sec_company_actual(spec, submissions_bytes)
    metrics = parse_sec_company_actual_html(spec, filing_bytes)
    submissions_sha256 = hashlib.sha256(submissions_bytes).hexdigest()
    filing_sha256 = hashlib.sha256(filing_bytes).hexdigest()
    payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "document_id": spec.document_id,
        "ticker": spec.ticker,
        "accession_number": discovered.accession_number,
        "primary_document": discovered.primary_document,
        "filing_date": discovered.filing_date.isoformat(),
        "period_start": spec.period_start.isoformat(),
        "period_end": spec.period_end.isoformat(),
        "submissions_url": spec.submissions_url,
        "filing_url": spec.filing_url,
        "submissions_sha256": submissions_sha256,
        "filing_sha256": filing_sha256,
        "unit": metrics.unit,
        "revenue": metrics.revenue,
        "operating_income": metrics.operating_income,
        "net_income": metrics.net_income,
        "company_level_actual": True,
        "provisional": True,
        "audited": False,
        "product_baseline_eligible": False,
        "source_bytes_archived": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    evidence_id = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return SecCompanyActualEvidence(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        document_id=spec.document_id,
        ticker=spec.ticker,
        issuer_name=spec.issuer_name,
        accession_number=discovered.accession_number,
        primary_document=discovered.primary_document,
        filing_date=discovered.filing_date,
        period_start=spec.period_start,
        period_end=spec.period_end,
        submissions_url=spec.submissions_url,
        filing_url=spec.filing_url,
        submissions_sha256=submissions_sha256,
        filing_sha256=filing_sha256,
        metrics=metrics,
    )


def collect_sec_company_actual(
    spec: SecCompanyActualSpec,
    *,
    evaluation_date: date,
    user_agent: str,
    timeout_seconds: float = 20.0,
) -> tuple[SecCompanyActualEvidence, bytes, bytes]:
    submissions_bytes = download_sec_bytes(
        spec.submissions_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    discover_sec_company_actual(spec, submissions_bytes)
    filing_bytes = download_sec_bytes(
        spec.filing_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    evidence = build_sec_company_actual_evidence(
        spec,
        evaluation_date=evaluation_date,
        submissions_bytes=submissions_bytes,
        filing_bytes=filing_bytes,
    )
    return evidence, submissions_bytes, filing_bytes


__all__ = [
    "DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY",
    "SEC_ARCHIVES_ROOT",
    "SEC_SUBMISSIONS_ROOT",
    "SecCompanyActualEvidence",
    "SecCompanyActualMetrics",
    "SecCompanyActualSpec",
    "SecDiscoveredFiling",
    "build_sec_company_actual_evidence",
    "collect_sec_company_actual",
    "discover_sec_company_actual",
    "download_sec_bytes",
    "extract_sec_visible_parts",
    "load_sec_company_actual_registry",
    "parse_sec_company_actual_html",
    "validate_sec_user_agent",
]
