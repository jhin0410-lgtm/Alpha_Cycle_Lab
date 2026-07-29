"""Read-only OpenDART financial-statement and disclosure adapter."""

from __future__ import annotations

import hashlib
import io
import os
import time
import zipfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import cast
from urllib.parse import urlencode
from xml.etree import ElementTree

import pandas as pd

from alpha_cycle.data.research import validate_financial_statements
from alpha_cycle.providers.read_only_http import (
    HttpBytesTransport,
    RetryingReadOnlyClient,
    decode_json,
)

OPENDART_BASE_URL = "https://opendart.fss.or.kr"
REPORT_PERIODS = {
    "11013": ("Q1", 3, 31),
    "11012": ("H1", 6, 30),
    "11014": ("Q3", 9, 30),
    "11011": ("FY", 12, 31),
}
MAX_DISCLOSURE_PAGES = 1000
NO_DATA_STATUS = "013"


@dataclass(frozen=True)
class OpenDartCredentials:
    """OpenDART key loaded only from local environment variables."""

    api_key: str
    base_url: str = OPENDART_BASE_URL

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> OpenDartCredentials:
        values = os.environ if environ is None else environ
        api_key = values.get("OPENDART_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENDART_API_KEY must be set locally")
        if "replace_with" in api_key.lower():
            raise ValueError("OpenDART placeholder credentials cannot be used")
        return cls(api_key=api_key)

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != OPENDART_BASE_URL:
            raise ValueError("Only the official OpenDART API host is allowed")


@dataclass(frozen=True)
class CorpCode:
    corp_code: str
    corp_name: str
    stock_code: str
    modify_date: date


@dataclass(frozen=True)
class CorpCodeArchiveDiagnostics:
    """Sanitized counts describing how the corporation archive was parsed."""

    total_rows: int
    listed_rows: int
    accepted_rows: int
    skipped_invalid_stock_codes: int
    skipped_invalid_metadata: int
    duplicate_stock_codes: int

    def as_dict(self) -> dict[str, int]:
        return {
            "total_rows": self.total_rows,
            "listed_rows": self.listed_rows,
            "accepted_rows": self.accepted_rows,
            "skipped_invalid_stock_codes": self.skipped_invalid_stock_codes,
            "skipped_invalid_metadata": self.skipped_invalid_metadata,
            "duplicate_stock_codes": self.duplicate_stock_codes,
        }


@dataclass(frozen=True)
class DisclosureBatch:
    frame: pd.DataFrame
    raw_payload: object


@dataclass(frozen=True)
class FinancialBatch:
    frame: pd.DataFrame
    raw_payload: object
    corp: CorpCode


def _date_yyyymmdd(value: object, field: str) -> date:
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYYMMDD") from exc


def _dart_status(
    payload: Mapping[str, object],
    *,
    endpoint: str,
    allow_no_data: bool = False,
) -> str:
    status = str(payload.get("status", "")).strip()
    if status == "000":
        return status
    if allow_no_data and status == NO_DATA_STATUS:
        return status
    message = str(payload.get("message", "request failed")).strip()
    raise ValueError(f"OpenDART {endpoint} failed: status={status or 'unknown'} message={message}")


def _parse_amount(value: object) -> Decimal | None:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"OpenDART financial amount is invalid: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError("OpenDART financial amount must be finite")
    return -amount if negative else amount


def _node_text(node: ElementTree.Element, name: str) -> str:
    child = node.find(name)
    return "" if child is None or child.text is None else child.text.strip()


def _normalize_archive_stock_code(value: object) -> str | None:
    text = str(value).strip().upper()
    if not text:
        return None
    if len(text) == 7 and text.startswith("A") and text[1:].isdigit():
        text = text[1:]
    if not text.isdigit() or len(text) not in {5, 6}:
        return None
    return text.zfill(6)


def normalize_listed_stock_code(value: object) -> str:
    """Return one canonical six-digit KRX code or fail with actionable context."""

    text = str(value).strip().upper()
    if len(text) == 7 and text.startswith("A") and text[1:].isdigit():
        text = text[1:]
    if not text.isdigit() or not 1 <= len(text) <= 6:
        raise ValueError("OpenDART listed stock codes must be numeric and at most six digits")
    return text.zfill(6)


def _safe_int(value: object, field: str) -> int:
    try:
        result = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"OpenDART {field} must be an integer") from exc
    return result


def _archive_xml(body: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            xml_names = [
                name
                for name in archive.namelist()
                if not name.endswith("/") and name.lower().endswith(".xml")
            ]
            if len(xml_names) != 1:
                raise ValueError("OpenDART corporation archive must contain one XML file")
            return archive.read(xml_names[0])
    except zipfile.BadZipFile:
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as exc:
            raise ValueError("OpenDART corporation-code archive is neither ZIP nor XML") from exc
        status = _node_text(root, "status")
        message = _node_text(root, "message") or "request failed"
        if status:
            raise ValueError(
                f"OpenDART /api/corpCode.xml failed: status={status} message={message}"
            ) from None
        raise ValueError("OpenDART corporation-code archive is invalid") from None


class OpenDartReadOnlyClient(RetryingReadOnlyClient):
    """Official OpenDART GET-only client normalized to project PIT contracts."""

    def __init__(
        self,
        credentials: OpenDartCredentials,
        *,
        transport: HttpBytesTransport | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__(
            transport=transport,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            sleep=sleep,
        )
        self.credentials = credentials
        self.now = now
        self._corp_cache: tuple[CorpCode, ...] | None = None
        self._corp_diagnostics: CorpCodeArchiveDiagnostics | None = None

    @classmethod
    def from_env(cls) -> OpenDartReadOnlyClient:
        return cls(OpenDartCredentials.from_env())

    @property
    def corp_code_diagnostics(self) -> CorpCodeArchiveDiagnostics | None:
        return self._corp_diagnostics

    def _url(self, path: str, query: Mapping[str, str]) -> str:
        if not path.startswith("/api/"):
            raise ValueError("OpenDART path must be a read-only /api route")
        params = {"crtfc_key": self.credentials.api_key, **dict(query)}
        return f"{self.credentials.base_url}{path}?{urlencode(params)}"

    def _json_get(
        self,
        path: str,
        query: Mapping[str, str],
        *,
        allow_no_data: bool = False,
    ) -> Mapping[str, object]:
        response = self._get(self._url(path, query))
        if response.status != 200:
            raise ValueError(f"OpenDART HTTP {response.status}: endpoint={path}")
        payload = decode_json(response.body, provider="OpenDART")
        if not isinstance(payload, dict):
            raise ValueError("OpenDART JSON response must be an object")
        result = cast(Mapping[str, object], payload)
        _dart_status(result, endpoint=path, allow_no_data=allow_no_data)
        return result

    def corp_codes(self, *, force: bool = False) -> tuple[CorpCode, ...]:
        if self._corp_cache is not None and not force:
            return self._corp_cache
        response = self._get(self._url("/api/corpCode.xml", {}))
        if response.status != 200:
            raise ValueError(f"OpenDART HTTP {response.status}: endpoint=/api/corpCode.xml")
        xml_bytes = _archive_xml(response.body)
        try:
            root = ElementTree.fromstring(xml_bytes)
        except ElementTree.ParseError as exc:
            raise ValueError("OpenDART corporation-code XML is invalid") from exc

        rows: list[CorpCode] = []
        total_rows = 0
        listed_rows = 0
        invalid_stock = 0
        invalid_metadata = 0
        for node in root.findall("list"):
            total_rows += 1
            raw_stock_code = _node_text(node, "stock_code")
            if not raw_stock_code:
                continue
            listed_rows += 1
            stock_code = _normalize_archive_stock_code(raw_stock_code)
            if stock_code is None:
                invalid_stock += 1
                continue
            corp_code = _node_text(node, "corp_code")
            corp_name = _node_text(node, "corp_name")
            if len(corp_code) != 8 or not corp_code.isdigit() or not corp_name:
                invalid_metadata += 1
                continue
            try:
                modify_date = _date_yyyymmdd(_node_text(node, "modify_date"), "modify_date")
            except ValueError:
                invalid_metadata += 1
                continue
            rows.append(
                CorpCode(
                    corp_code=corp_code,
                    corp_name=corp_name,
                    stock_code=stock_code,
                    modify_date=modify_date,
                )
            )
        if not rows:
            raise ValueError(
                "OpenDART corporation archive contains no usable listed companies "
                f"(listed_rows={listed_rows}, invalid_stock_codes={invalid_stock}, "
                f"invalid_metadata={invalid_metadata})"
            )
        counts = Counter(item.stock_code for item in rows)
        duplicates = sum(1 for count in counts.values() if count > 1)
        self._corp_diagnostics = CorpCodeArchiveDiagnostics(
            total_rows=total_rows,
            listed_rows=listed_rows,
            accepted_rows=len(rows),
            skipped_invalid_stock_codes=invalid_stock,
            skipped_invalid_metadata=invalid_metadata,
            duplicate_stock_codes=duplicates,
        )
        self._corp_cache = tuple(
            sorted(rows, key=lambda item: (item.stock_code, item.modify_date, item.corp_code))
        )
        return self._corp_cache

    def resolve_stock_codes(self, symbols: Sequence[str]) -> dict[str, CorpCode]:
        normalized = tuple(
            dict.fromkeys(
                normalize_listed_stock_code(symbol)
                for symbol in symbols
                if str(symbol).strip()
            )
        )
        if not normalized:
            raise ValueError("At least one listed stock code is required")
        candidates: dict[str, list[CorpCode]] = {}
        for item in self.corp_codes():
            candidates.setdefault(item.stock_code, []).append(item)

        missing = [symbol for symbol in normalized if symbol not in candidates]
        if missing:
            diagnostics = self._corp_diagnostics
            suffix = ""
            if diagnostics is not None:
                suffix = (
                    f"; archive_skipped_invalid_stock_codes="
                    f"{diagnostics.skipped_invalid_stock_codes}"
                )
            raise ValueError(
                f"OpenDART corporation code not found for: {','.join(missing)}{suffix}"
            )

        resolved: dict[str, CorpCode] = {}
        for symbol in normalized:
            options = candidates[symbol]
            latest_date = max(item.modify_date for item in options)
            latest = [item for item in options if item.modify_date == latest_date]
            unique_codes = {item.corp_code for item in latest}
            if len(unique_codes) > 1:
                raise ValueError(
                    "OpenDART corporation archive is ambiguous for "
                    f"{symbol}: {len(unique_codes)} corp codes share modify_date={latest_date}"
                )
            resolved[symbol] = sorted(latest, key=lambda item: item.corp_code)[0]
        return resolved

    def company(self, corp_code: str) -> Mapping[str, object]:
        if len(corp_code) != 8 or not corp_code.isdigit():
            raise ValueError("OpenDART corp_code must be eight digits")
        return self._json_get("/api/company.json", {"corp_code": corp_code})

    def disclosures(
        self,
        corp: CorpCode,
        *,
        begin_date: date,
        end_date: date,
    ) -> DisclosureBatch:
        if begin_date > end_date:
            raise ValueError("OpenDART disclosure begin_date cannot follow end_date")
        columns = [
            "ticker",
            "corp_code",
            "corp_name",
            "rcept_no",
            "report_name",
            "receipt_date",
            "corp_class",
            "is_correction",
        ]
        raw_pages: list[Mapping[str, object]] = []
        records: dict[str, dict[str, object]] = {}
        page_no = 1
        total_pages = 1
        while page_no <= total_pages:
            payload = self._json_get(
                "/api/list.json",
                {
                    "corp_code": corp.corp_code,
                    "bgn_de": begin_date.strftime("%Y%m%d"),
                    "end_de": end_date.strftime("%Y%m%d"),
                    "page_no": str(page_no),
                    "page_count": "100",
                    "sort": "date",
                    "sort_mth": "asc",
                },
                allow_no_data=True,
            )
            raw_pages.append(payload)
            status = str(payload.get("status", "")).strip()
            if status == NO_DATA_STATUS:
                break
            if page_no == 1:
                total_pages = _safe_int(payload.get("total_page", 1), "total_page")
                if total_pages < 1 or total_pages > MAX_DISCLOSURE_PAGES:
                    raise ValueError(
                        "OpenDART disclosure total_page is outside the supported range: "
                        f"{total_pages}"
                    )
            raw_rows = payload.get("list", [])
            if not isinstance(raw_rows, list):
                raise ValueError("OpenDART disclosure list must be an array")
            for raw in raw_rows:
                if not isinstance(raw, dict):
                    raise ValueError("OpenDART disclosure row must be an object")
                rcept_no = str(raw.get("rcept_no", "")).strip()
                if len(rcept_no) != 14 or not rcept_no.isdigit():
                    raise ValueError("OpenDART receipt number must be 14 digits")
                report_name = str(raw.get("report_nm", "")).strip()
                receipt_text = str(raw.get("rcept_dt", "")).strip() or rcept_no[:8]
                record = {
                    "ticker": corp.stock_code,
                    "corp_code": corp.corp_code,
                    "corp_name": str(raw.get("corp_name", corp.corp_name)).strip(),
                    "rcept_no": rcept_no,
                    "report_name": report_name,
                    "receipt_date": _date_yyyymmdd(receipt_text, "rcept_dt"),
                    "corp_class": str(raw.get("corp_cls", "")).strip(),
                    "is_correction": "정정" in report_name,
                }
                existing = records.get(rcept_no)
                if existing is not None and existing != record:
                    raise ValueError(
                        f"OpenDART disclosure pages conflict for receipt number {rcept_no}"
                    )
                records[rcept_no] = record
            page_no += 1

        frame = pd.DataFrame(list(records.values()), columns=columns)
        if not frame.empty:
            frame = frame.sort_values(["receipt_date", "rcept_no"], kind="stable")
        raw_payload = {
            "pages": [dict(page) for page in raw_pages],
            "page_count": len(raw_pages),
        }
        return DisclosureBatch(frame.reset_index(drop=True), raw_payload)

    def financial_statements(
        self,
        corp: CorpCode,
        *,
        business_year: int,
        report_code: str,
        fs_div: str = "CFS",
    ) -> FinancialBatch:
        if report_code not in REPORT_PERIODS:
            raise ValueError("OpenDART report_code is unsupported")
        if fs_div not in {"CFS", "OFS"}:
            raise ValueError("OpenDART fs_div must be CFS or OFS")
        company = self.company(corp.corp_code)
        company_stock_code = str(company.get("stock_code", "")).strip()
        if company_stock_code:
            normalized_company_code = normalize_listed_stock_code(company_stock_code)
            if normalized_company_code != corp.stock_code:
                raise ValueError(
                    "OpenDART company stock_code does not match the corporation archive: "
                    f"expected={corp.stock_code}, actual={normalized_company_code}"
                )
        settlement_month = str(company.get("acc_mt", "")).strip().zfill(2)
        if settlement_month != "12":
            raise ValueError(
                "OpenDART financial normalization currently requires a December fiscal year"
            )
        payload = self._json_get(
            "/api/fnlttSinglAcntAll.json",
            {
                "corp_code": corp.corp_code,
                "bsns_year": str(business_year),
                "reprt_code": report_code,
                "fs_div": fs_div,
            },
        )
        raw_rows = payload.get("list", [])
        if not isinstance(raw_rows, list):
            raise ValueError("OpenDART financial list must be an array")
        fiscal_period, month, day = REPORT_PERIODS[report_code]
        period_end = date(business_year, month, day)
        retrieved_at = self.now()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("OpenDART client clock must be timezone-aware")
        rows: list[dict[str, object]] = []
        for raw in raw_rows:
            if not isinstance(raw, dict):
                raise ValueError("OpenDART financial row must be an object")
            row_stock_code = str(raw.get("stock_code", "")).strip()
            if row_stock_code and normalize_listed_stock_code(row_stock_code) != corp.stock_code:
                raise ValueError("OpenDART financial row stock_code does not match the request")
            amount = _parse_amount(raw.get("thstrm_amount"))
            if amount is None:
                continue
            receipt_no = str(raw.get("rcept_no", "")).strip()
            if len(receipt_no) != 14 or not receipt_no.isdigit():
                raise ValueError("OpenDART financial receipt number must be 14 digits")
            statement = str(raw.get("sj_div", "")).strip()
            account_id = str(raw.get("account_id", "")).strip()
            account_name = str(raw.get("account_nm", "")).strip()
            if not statement or not account_name:
                raise ValueError("OpenDART financial statement and account name are required")
            account_key = account_id if account_id not in {"", "-"} else account_name
            detail = str(raw.get("account_detail", "")).strip()
            order = str(raw.get("ord", "")).strip()
            suffix = f":{detail}" if detail and detail != "-" else ""
            if order:
                suffix = f"{suffix}#{order}"
            rows.append(
                {
                    "ticker": corp.stock_code,
                    "metric": f"{statement}:{account_key}{suffix}",
                    "period_end": period_end,
                    "fiscal_period": fiscal_period,
                    "value": amount,
                    "unit": "KRW",
                    "available_date": _date_yyyymmdd(receipt_no[:8], "rcept_no date"),
                    "retrieved_at": retrieved_at,
                    "source": "opendart",
                    "revision_id": receipt_no,
                    "revision_sequence": 0,
                    "period_start": pd.NA,
                    "currency": "KRW",
                }
            )
        if not rows:
            raise ValueError("OpenDART returned no numeric current-term financial facts")
        frame = validate_financial_statements(pd.DataFrame(rows))
        raw_payload = {"company": dict(company), "financials": payload}
        return FinancialBatch(frame=frame, raw_payload=raw_payload, corp=corp)


def financial_frame_digest(frame: pd.DataFrame) -> str:
    """Stable digest used by research snapshots and tests."""

    csv_text = frame.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
