"""Inventory post-earnings SK hynix SEC primary HTML filings across all forms.

This is a discovery-only layer. It deliberately lives beside, rather than replacing, the
v1 6-K scout so previously captured v1 evidence identities and classifier semantics remain
stable. The inventory archives exact SEC submissions metadata and primary HTML bytes, then
classifies broad Q2/product-mix anchors. It never promotes a filing into a semiconductor
baseline or registers an allocation resolver.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.sec_company_actual import (
    SEC_ARCHIVES_ROOT,
    SEC_SUBMISSIONS_ROOT,
    download_sec_bytes,
    extract_sec_visible_parts,
)

SK_HYNIX_TICKER = "000660"
SK_HYNIX_CIK = "0002120882"
DEFAULT_ALL_FORM_AFTER_DATE = date(2026, 7, 29)
DEFAULT_SEC_ALL_FORM_INVENTORY_OUTPUT = Path(
    "data/private/research/sec-post-earnings-all-form-inventory"
)
DEFAULT_SEC_ALL_FORM_INVENTORY_POINTER = (
    DEFAULT_SEC_ALL_FORM_INVENTORY_OUTPUT / "latest_sec_post_earnings_all_form_inventory.json"
)
_KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")

_Q2_ANCHORS = (
    "second quarter of 2026",
    "second quarter 2026",
    "2q26",
    "2q 2026",
    "three months ended june 30, 2026",
    "three months ended june 30 2026",
    "quarter ended june 30, 2026",
    "quarter ended june 30 2026",
)
_DRAM_ANCHORS = ("dram",)
_NAND_ANCHORS = ("nand", "nand flash")
_OTHER_ANCHORS = ("other products", "other product")
_REVENUE_ANCHORS = ("revenue", "sales")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _valid_accession(value: str) -> bool:
    parts = value.split("-")
    return bool(
        len(parts) == 3
        and tuple(len(item) for item in parts) == (10, 2, 6)
        and all(item.isdigit() for item in parts)
    )


@dataclass(frozen=True)
class SecPostEarningsHtmlFiling:
    accession_number: str
    filing_date: date
    form: str
    primary_document: str

    def __post_init__(self) -> None:
        if not _valid_accession(self.accession_number):
            raise ValueError("SEC all-form inventory accession number is invalid")
        if not self.form.strip():
            raise ValueError("SEC all-form inventory filing form is empty")
        if Path(self.primary_document).name != self.primary_document:
            raise ValueError("SEC all-form inventory primary document path is unsafe")
        if not self.primary_document.casefold().endswith((".htm", ".html")):
            raise ValueError("SEC all-form inventory primary document must be HTML")

    @property
    def filing_url(self) -> str:
        accession = self.accession_number.replace("-", "")
        return (
            f"{SEC_ARCHIVES_ROOT}/{int(SK_HYNIX_CIK)}/{accession}/"
            f"{self.primary_document}"
        )


@dataclass(frozen=True)
class SecPostEarningsHtmlResult:
    accession_number: str
    filing_date: date
    form: str
    primary_document: str
    filing_sha256: str
    filing_bytes: int
    visible_text_sha256: str
    visible_text_chars: int
    q2_period_anchor: bool
    dram_anchor: bool
    nand_anchor: bool
    other_products_anchor: bool
    revenue_anchor: bool
    classification: str
    candidate_for_manual_parser_review: bool
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.filing_sha256) or not _valid_sha(self.visible_text_sha256):
            raise ValueError("SEC all-form inventory result hashes must be SHA-256")
        allowed = {
            "no_product_mix_signal",
            "memory_mentions_only",
            "q2_memory_candidate",
            "q2_full_revenue_candidate",
        }
        if self.classification not in allowed:
            raise ValueError("SEC all-form inventory classification is invalid")
        expected_candidate = self.classification in {
            "q2_memory_candidate",
            "q2_full_revenue_candidate",
        }
        if self.candidate_for_manual_parser_review != expected_candidate:
            raise ValueError("SEC all-form inventory candidate flag does not match classification")
        if (
            self.product_baseline_eligible
            or self.allocation_resolver_registered
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SEC all-form inventory cannot widen model or scoring trust")


@dataclass(frozen=True)
class SecPostEarningsAllFormEvidence:
    evidence_id: str
    observed_date: date
    after_date: date
    submissions_sha256: str
    filings: tuple[SecPostEarningsHtmlFiling, ...]
    results: tuple[SecPostEarningsHtmlResult, ...]
    discovery_only: bool = True
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.submissions_sha256):
            raise ValueError("SEC all-form inventory evidence hashes must be SHA-256")
        if self.after_date >= self.observed_date:
            raise ValueError("SEC all-form inventory observed_date must be after cutoff")
        filing_ids = tuple(item.accession_number for item in self.filings)
        result_ids = tuple(item.accession_number for item in self.results)
        if filing_ids != result_ids:
            raise ValueError("SEC all-form inventory filing/result identities do not align")
        if not self.discovery_only:
            raise ValueError("SEC all-form inventory must remain discovery-only")
        if (
            self.product_baseline_eligible
            or self.allocation_resolver_registered
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SEC all-form inventory evidence exceeds its trust boundary")


def _recent_columns(submissions_bytes: bytes) -> dict[str, list[object]]:
    try:
        payload: object = json.loads(submissions_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SEC all-form submissions payload is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("SEC all-form submissions payload must be an object")
    root = cast(dict[str, object], payload)
    if str(root.get("cik", "")).zfill(10) != SK_HYNIX_CIK:
        raise ValueError("SEC all-form submissions payload is not SK hynix")
    filings = root.get("filings")
    if not isinstance(filings, dict):
        raise ValueError("SEC all-form submissions payload is missing filings")
    recent = cast(dict[str, object], filings).get("recent")
    if not isinstance(recent, dict):
        raise ValueError("SEC all-form submissions payload is missing recent filings")
    recent_map = cast(dict[str, object], recent)
    required = ("accessionNumber", "filingDate", "form", "primaryDocument")
    columns: dict[str, list[object]] = {}
    for key in required:
        raw = recent_map.get(key)
        if not isinstance(raw, list):
            raise ValueError(f"SEC all-form submissions recent.{key} must be an array")
        columns[key] = raw
    lengths = {len(items) for items in columns.values()}
    if len(lengths) != 1:
        raise ValueError("SEC all-form recent filing arrays are misaligned")
    return columns


def discover_post_earnings_primary_html_filings(
    submissions_bytes: bytes,
    *,
    after_date: date = DEFAULT_ALL_FORM_AFTER_DATE,
    observed_date: date,
) -> tuple[SecPostEarningsHtmlFiling, ...]:
    if observed_date <= after_date:
        raise ValueError("SEC all-form observed_date must be after cutoff")
    columns = _recent_columns(submissions_bytes)
    discovered: list[SecPostEarningsHtmlFiling] = []
    for index in range(len(columns["accessionNumber"])):
        filing_date = date.fromisoformat(str(columns["filingDate"][index]).strip())
        if filing_date <= after_date or filing_date > observed_date:
            continue
        primary_document = str(columns["primaryDocument"][index]).strip()
        if not primary_document.casefold().endswith((".htm", ".html")):
            continue
        discovered.append(
            SecPostEarningsHtmlFiling(
                accession_number=str(columns["accessionNumber"][index]).strip(),
                filing_date=filing_date,
                form=str(columns["form"][index]).strip(),
                primary_document=primary_document,
            )
        )
    discovered.sort(
        key=lambda item: (item.filing_date, item.accession_number),
        reverse=True,
    )
    return tuple(discovered)


def _contains_any(text: str, anchors: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(anchor.casefold() in lowered for anchor in anchors)


def classify_post_earnings_primary_html(
    filing: SecPostEarningsHtmlFiling,
    filing_bytes: bytes,
) -> SecPostEarningsHtmlResult:
    visible_text = " ".join(extract_sec_visible_parts(filing_bytes))
    normalized = " ".join(visible_text.split())
    q2 = _contains_any(normalized, _Q2_ANCHORS)
    dram = _contains_any(normalized, _DRAM_ANCHORS)
    nand = _contains_any(normalized, _NAND_ANCHORS)
    other = _contains_any(normalized, _OTHER_ANCHORS)
    revenue = _contains_any(normalized, _REVENUE_ANCHORS)
    if q2 and dram and nand and other and revenue:
        classification = "q2_full_revenue_candidate"
    elif q2 and dram and nand:
        classification = "q2_memory_candidate"
    elif dram or nand or other:
        classification = "memory_mentions_only"
    else:
        classification = "no_product_mix_signal"
    return SecPostEarningsHtmlResult(
        accession_number=filing.accession_number,
        filing_date=filing.filing_date,
        form=filing.form,
        primary_document=filing.primary_document,
        filing_sha256=_sha_bytes(filing_bytes),
        filing_bytes=len(filing_bytes),
        visible_text_sha256=_sha_bytes(normalized.encode("utf-8")),
        visible_text_chars=len(normalized),
        q2_period_anchor=q2,
        dram_anchor=dram,
        nand_anchor=nand,
        other_products_anchor=other,
        revenue_anchor=revenue,
        classification=classification,
        candidate_for_manual_parser_review=classification
        in {"q2_memory_candidate", "q2_full_revenue_candidate"},
    )


def build_post_earnings_all_form_evidence(
    *,
    observed_date: date,
    after_date: date,
    submissions_bytes: bytes,
    filing_bytes_by_accession: dict[str, bytes],
) -> SecPostEarningsAllFormEvidence:
    filings = discover_post_earnings_primary_html_filings(
        submissions_bytes,
        after_date=after_date,
        observed_date=observed_date,
    )
    expected_accessions = {item.accession_number for item in filings}
    if set(filing_bytes_by_accession) != expected_accessions:
        raise ValueError("SEC all-form filing byte set must match discovered filings exactly")
    results = tuple(
        classify_post_earnings_primary_html(
            item,
            filing_bytes_by_accession[item.accession_number],
        )
        for item in filings
    )
    payload = {
        "observed_date": observed_date.isoformat(),
        "after_date": after_date.isoformat(),
        "submissions_sha256": _sha_bytes(submissions_bytes),
        "results": [
            {
                "accession_number": item.accession_number,
                "form": item.form,
                "filing_sha256": item.filing_sha256,
                "classification": item.classification,
            }
            for item in results
        ],
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return SecPostEarningsAllFormEvidence(
        evidence_id=_sha_payload(payload),
        observed_date=observed_date,
        after_date=after_date,
        submissions_sha256=_sha_bytes(submissions_bytes),
        filings=filings,
        results=results,
    )


def _result_payload(item: SecPostEarningsHtmlResult) -> dict[str, object]:
    return {
        "accession_number": item.accession_number,
        "filing_date": item.filing_date.isoformat(),
        "form": item.form,
        "primary_document": item.primary_document,
        "filing_sha256": item.filing_sha256,
        "filing_bytes": item.filing_bytes,
        "visible_text_sha256": item.visible_text_sha256,
        "visible_text_chars": item.visible_text_chars,
        "q2_period_anchor": item.q2_period_anchor,
        "dram_anchor": item.dram_anchor,
        "nand_anchor": item.nand_anchor,
        "other_products_anchor": item.other_products_anchor,
        "revenue_anchor": item.revenue_anchor,
        "classification": item.classification,
        "candidate_for_manual_parser_review": item.candidate_for_manual_parser_review,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def _form_counts(results: tuple[SecPostEarningsHtmlResult, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        counts[item.form] = counts.get(item.form, 0) + 1
    return dict(sorted(counts.items()))


def capture_post_earnings_all_form_inventory(
    *,
    observed_date: date,
    user_agent: str,
    after_date: date = DEFAULT_ALL_FORM_AFTER_DATE,
    output: str | Path = DEFAULT_SEC_ALL_FORM_INVENTORY_OUTPUT,
    captured_at: datetime | None = None,
    timeout_seconds: float = 20.0,
) -> dict[str, object]:
    submissions_url = f"{SEC_SUBMISSIONS_ROOT}/CIK{SK_HYNIX_CIK}.json"
    submissions_bytes = download_sec_bytes(
        submissions_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    filings = discover_post_earnings_primary_html_filings(
        submissions_bytes,
        after_date=after_date,
        observed_date=observed_date,
    )
    filing_bytes_by_accession: dict[str, bytes] = {}
    for filing in filings:
        filing_bytes_by_accession[filing.accession_number] = download_sec_bytes(
            filing.filing_url,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
        )
    evidence = build_post_earnings_all_form_evidence(
        observed_date=observed_date,
        after_date=after_date,
        submissions_bytes=submissions_bytes,
        filing_bytes_by_accession=filing_bytes_by_accession,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if captured.astimezone(_KOREA_TIME_ZONE).date() < observed_date:
        raise ValueError("captured_at cannot precede observed_date in Asia/Seoul")

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"SEC all-form inventory artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        (temporary / "sec_submissions.json").write_bytes(submissions_bytes)
        filing_files: list[str] = []
        for filing in evidence.filings:
            safe_name = f"{filing.accession_number}__{filing.primary_document}"
            filing_files.append(safe_name)
            (temporary / safe_name).write_bytes(
                filing_bytes_by_accession[filing.accession_number]
            )
        results_payload = [_result_payload(item) for item in evidence.results]
        (temporary / "inventory_results.json").write_text(
            json.dumps(results_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        candidate_accessions = [
            item.accession_number
            for item in evidence.results
            if item.candidate_for_manual_parser_review
        ]
        manifest = {
            "schema_version": 1,
            "status": "sec_post_earnings_all_form_inventory_captured",
            "evidence_id": evidence.evidence_id,
            "observed_date": evidence.observed_date.isoformat(),
            "after_date": evidence.after_date.isoformat(),
            "ticker": SK_HYNIX_TICKER,
            "cik": SK_HYNIX_CIK,
            "submissions_sha256": evidence.submissions_sha256,
            "filing_count": len(evidence.filings),
            "non_6k_filing_count": sum(item.form != "6-K" for item in evidence.results),
            "form_counts": _form_counts(evidence.results),
            "candidate_count": len(candidate_accessions),
            "candidate_accessions": candidate_accessions,
            "discovery_only": True,
            "product_baseline_eligible": False,
            "allocation_resolver_registered": False,
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
            "captured_at": captured.isoformat(),
            "files": ["sec_submissions.json", "inventory_results.json", *filing_files],
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    candidate_accessions = [
        item.accession_number
        for item in evidence.results
        if item.candidate_for_manual_parser_review
    ]
    pointer = {
        "schema_version": 1,
        "status": "sec_post_earnings_all_form_inventory_captured",
        "evidence_id": evidence.evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "after_date": evidence.after_date.isoformat(),
        "ticker": SK_HYNIX_TICKER,
        "cik": SK_HYNIX_CIK,
        "submissions_sha256": evidence.submissions_sha256,
        "filing_count": len(evidence.filings),
        "non_6k_filing_count": sum(item.form != "6-K" for item in evidence.results),
        "form_counts": _form_counts(evidence.results),
        "candidate_count": len(candidate_accessions),
        "candidate_accessions": candidate_accessions,
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "manifest_path": str((directory / "manifest.json").resolve()),
        "inventory_results_path": str((directory / "inventory_results.json").resolve()),
        "artifact_directory": str(directory.resolve()),
    }
    pointer_path = root / "latest_sec_post_earnings_all_form_inventory.json"
    temporary_pointer = root / ".latest_sec_post_earnings_all_form_inventory.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return pointer


__all__ = [
    "DEFAULT_ALL_FORM_AFTER_DATE",
    "DEFAULT_SEC_ALL_FORM_INVENTORY_OUTPUT",
    "DEFAULT_SEC_ALL_FORM_INVENTORY_POINTER",
    "SK_HYNIX_CIK",
    "SK_HYNIX_TICKER",
    "SecPostEarningsAllFormEvidence",
    "SecPostEarningsHtmlFiling",
    "SecPostEarningsHtmlResult",
    "build_post_earnings_all_form_evidence",
    "capture_post_earnings_all_form_inventory",
    "classify_post_earnings_primary_html",
    "discover_post_earnings_primary_html_filings",
]
