"""Historical SK hynix product-mix calibration from official SEC filing bytes.

This evidence is deliberately retrospective. It verifies whether the direct-share
allocation method reproduces product revenue that the issuer later disclosed directly.
It never substitutes 1Q26 product mix for a current-quarter baseline and never creates a
residual "other" source fact from DRAM/NAND percentages.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.sec_company_actual import (
    SEC_ARCHIVES_ROOT,
    SEC_SUBMISSIONS_ROOT,
    download_sec_bytes,
    extract_sec_visible_parts,
)

DEFAULT_SEC_PRODUCT_MIX_REGISTRY = Path(
    "config/semiconductor_sec_product_mix_calibration.yaml"
)
DEFAULT_SEC_PRODUCT_MIX_OUTPUT = Path(
    "data/private/research/sec-product-mix-calibration"
)
DEFAULT_SEC_PRODUCT_MIX_POINTER = (
    DEFAULT_SEC_PRODUCT_MIX_OUTPUT / "latest_sec_product_mix_calibration.json"
)
_SHARE_METHOD_RELATIVE_TOLERANCE = 0.001


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


@dataclass(frozen=True)
class SecProductMixCalibrationSpec:
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
    historical_calibration_only: bool
    current_baseline_eligible: bool
    q2_allocation_eligible: bool
    required_identity_anchors: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.ticker != "000660":
            raise ValueError("SEC product-mix calibration v1 supports SK hynix only")
        if self.source_id != "sec_edgar" or self.form != "424B4":
            raise ValueError("SEC product-mix calibration requires the official 424B4")
        if len(self.cik) != 10 or not self.cik.isdigit():
            raise ValueError("SEC product-mix calibration CIK must be ten digits")
        parts = self.expected_accession_number.split("-")
        if (
            len(parts) != 3
            or tuple(len(item) for item in parts) != (10, 2, 6)
            or not all(item.isdigit() for item in parts)
        ):
            raise ValueError("SEC product-mix calibration accession is invalid")
        if not self.expected_primary_document.endswith((".htm", ".html")):
            raise ValueError("SEC product-mix calibration primary document must be HTML")
        if self.period_start > self.period_end or self.period_end > self.filing_date:
            raise ValueError("SEC product-mix calibration dates are invalid")
        if (
            not self.historical_calibration_only
            or self.current_baseline_eligible
            or self.q2_allocation_eligible
        ):
            raise ValueError("SEC product-mix calibration cannot become current evidence")
        if not self.required_identity_anchors:
            raise ValueError("SEC product-mix calibration requires identity anchors")

    @property
    def submissions_url(self) -> str:
        return f"{SEC_SUBMISSIONS_ROOT}/CIK{self.cik}.json"

    @property
    def filing_url(self) -> str:
        accession = self.expected_accession_number.replace("-", "")
        return (
            f"{SEC_ARCHIVES_ROOT}/{int(self.cik)}/{accession}/"
            f"{self.expected_primary_document}"
        )


@dataclass(frozen=True)
class SecProductMixMetrics:
    unit: str
    total_revenue: float
    dram_revenue: float
    nand_revenue: float
    other_products_revenue: float
    dram_share_percent: float
    nand_share_percent: float

    def __post_init__(self) -> None:
        if self.unit != "KRW_billion":
            raise ValueError("SEC product-mix calibration normalizes to KRW_billion")
        values = (
            self.total_revenue,
            self.dram_revenue,
            self.nand_revenue,
            self.other_products_revenue,
            self.dram_share_percent,
            self.nand_share_percent,
        )
        if any(not math.isfinite(item) for item in values):
            raise ValueError("SEC product-mix calibration values must be finite")
        if min(
            self.total_revenue,
            self.dram_revenue,
            self.nand_revenue,
            self.other_products_revenue,
        ) <= 0:
            raise ValueError("SEC product-mix revenue values must be positive")
        if not 0 < self.dram_share_percent < 100 or not 0 < self.nand_share_percent < 100:
            raise ValueError("SEC product-mix shares must be percentages")
        direct_sum = self.dram_revenue + self.nand_revenue + self.other_products_revenue
        if abs(direct_sum - self.total_revenue) > 1e-9:
            raise ValueError("SEC product-mix direct revenue table does not reconcile")
        dram_from_amount = self.dram_revenue / self.total_revenue * 100.0
        nand_from_amount = self.nand_revenue / self.total_revenue * 100.0
        if abs(dram_from_amount - self.dram_share_percent) > 0.05:
            raise ValueError("SEC DRAM share is inconsistent with directly reported revenue")
        if abs(nand_from_amount - self.nand_share_percent) > 0.05:
            raise ValueError("SEC NAND share is inconsistent with directly reported revenue")


@dataclass(frozen=True)
class SecProductMixCalibrationEvidence:
    evidence_id: str
    calibration_evidence_id: str
    observed_date: date
    document_id: str
    ticker: str
    issuer_name: str
    accession_number: str
    primary_document: str
    filing_date: date
    period_start: date
    period_end: date
    submissions_sha256: str
    filing_sha256: str
    metrics: SecProductMixMetrics
    dram_share_implied_revenue: float
    nand_share_implied_revenue: float
    dram_share_method_relative_error: float
    nand_share_method_relative_error: float
    direct_product_table_reconciled: bool
    direct_share_method_calibrated: bool
    other_products_revenue_directly_disclosed: bool
    share_only_company_reconciliation_eligible: bool = False
    historical_calibration_only: bool = True
    current_baseline_eligible: bool = False
    q2_allocation_eligible: bool = False
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.calibration_evidence_id,
            self.submissions_sha256,
            self.filing_sha256,
        )
        if any(not _valid_sha(item) for item in hashes):
            raise ValueError("SEC product-mix evidence hashes must be SHA-256")
        if self.filing_date > self.observed_date:
            raise ValueError("SEC product-mix evidence cannot be observed before filing")
        if not (
            self.direct_product_table_reconciled
            and self.direct_share_method_calibrated
            and self.other_products_revenue_directly_disclosed
            and self.historical_calibration_only
        ):
            raise ValueError("SEC product-mix required calibration flags are not certified")
        if (
            self.share_only_company_reconciliation_eligible
            or self.current_baseline_eligible
            or self.q2_allocation_eligible
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SEC product-mix calibration exceeds its trust boundary")


def _strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"SEC product-mix {label} must be boolean")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"SEC product-mix {label} must be an array")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if not result:
        raise ValueError(f"SEC product-mix {label} cannot be empty")
    return result


def load_sec_product_mix_registry(
    path: str | Path = DEFAULT_SEC_PRODUCT_MIX_REGISTRY,
) -> dict[str, SecProductMixCalibrationSpec]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("issuers"), dict):
        raise ValueError("SEC product-mix registry must contain issuers")
    result: dict[str, SecProductMixCalibrationSpec] = {}
    issuers = cast(dict[object, object], payload["issuers"])
    for raw_ticker, raw_issuer in issuers.items():
        ticker = str(raw_ticker).strip().zfill(6)
        if not isinstance(raw_issuer, dict):
            raise ValueError(f"SEC product-mix issuer must be an object: {ticker}")
        issuer = cast(dict[object, object], raw_issuer)
        filings = issuer.get("filings", {})
        if not isinstance(filings, dict):
            raise ValueError(f"SEC product-mix filings must be an object: {ticker}")
        for raw_id, raw_value in cast(dict[object, object], filings).items():
            document_id = str(raw_id).strip()
            if not isinstance(raw_value, dict):
                raise ValueError(f"SEC product-mix filing must be an object: {document_id}")
            raw = cast(dict[object, object], raw_value)
            spec = SecProductMixCalibrationSpec(
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
                historical_calibration_only=_strict_bool(
                    raw.get("historical_calibration_only"), "historical_calibration_only"
                ),
                current_baseline_eligible=_strict_bool(
                    raw.get("current_baseline_eligible"), "current_baseline_eligible"
                ),
                q2_allocation_eligible=_strict_bool(
                    raw.get("q2_allocation_eligible"), "q2_allocation_eligible"
                ),
                required_identity_anchors=_string_tuple(
                    raw.get("required_identity_anchors", []), "required_identity_anchors"
                ),
            )
            if document_id in result:
                raise ValueError(f"SEC product-mix filing is duplicated: {document_id}")
            result[document_id] = spec
    if not result:
        raise ValueError("SEC product-mix registry is empty")
    return result


def discover_sec_product_mix_filing(
    spec: SecProductMixCalibrationSpec,
    submissions_bytes: bytes,
) -> None:
    try:
        payload: object = json.loads(submissions_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SEC product-mix submissions payload is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("SEC product-mix submissions payload must be an object")
    filings = cast(dict[str, object], payload).get("filings")
    if not isinstance(filings, dict):
        raise ValueError("SEC product-mix submissions payload is missing filings")
    recent = cast(dict[str, object], filings).get("recent")
    if not isinstance(recent, dict):
        raise ValueError("SEC product-mix submissions payload is missing recent filings")
    recent_map = cast(dict[str, object], recent)
    keys = ("accessionNumber", "filingDate", "form", "primaryDocument")
    columns: dict[str, list[object]] = {}
    for key in keys:
        value = recent_map.get(key)
        if not isinstance(value, list):
            raise ValueError(f"SEC product-mix recent.{key} must be an array")
        columns[key] = value
    lengths = {len(item) for item in columns.values()}
    if len(lengths) != 1:
        raise ValueError("SEC product-mix recent filing arrays are misaligned")
    matches = 0
    for index in range(next(iter(lengths), 0)):
        if (
            str(columns["accessionNumber"][index]).strip()
            == spec.expected_accession_number
            and str(columns["filingDate"][index]).strip() == spec.filing_date.isoformat()
            and str(columns["form"][index]).strip() == spec.form
            and str(columns["primaryDocument"][index]).strip()
            == spec.expected_primary_document
        ):
            matches += 1
    if matches != 1:
        raise ValueError(
            "Pinned SEC product-mix filing must resolve exactly once: "
            f"count={matches}"
        )


def _joined_visible_text(filing_bytes: bytes) -> str:
    return " ".join(extract_sec_visible_parts(filing_bytes))


def _require_anchor(text: str, anchor: str) -> None:
    if " ".join(anchor.split()).casefold() not in " ".join(text.split()).casefold():
        raise ValueError(f"SEC product-mix identity anchor is missing: {anchor}")


def _number(section: str, pattern: str, label: str) -> float:
    match = re.search(pattern, section, flags=re.IGNORECASE)
    if match is None:
        raise ValueError(f"SEC product-mix number is missing: {label}")
    return float(match.group(1).replace(",", ""))


def parse_sec_product_mix_html(
    spec: SecProductMixCalibrationSpec,
    filing_bytes: bytes,
) -> SecProductMixMetrics:
    if spec.parser_id != "skhynix_sec_424b4_2026q1_product_mix_v1":
        raise ValueError("SEC product-mix parser received an unsupported parser_id")
    text = _joined_visible_text(filing_bytes)
    for anchor in spec.required_identity_anchors:
        _require_anchor(text, anchor)
    start_anchor = (
        "The following table presents a breakdown of our revenue by principal product "
        "category and changes therein for the first quarter of 2026 and the first quarter of 2025."
    )
    start = text.casefold().find(start_anchor.casefold())
    if start < 0:
        raise ValueError("SEC product-mix 1Q26 revenue table start is missing")
    end = text.casefold().find("our revenue increased by", start)
    if end < 0:
        raise ValueError("SEC product-mix 1Q26 revenue table end is missing")
    section = text[start:end]
    metrics = SecProductMixMetrics(
        unit="KRW_billion",
        dram_revenue=_number(section, r"\bDRAM\s+(?:W\s+)?([0-9][0-9,]*)", "dram_revenue"),
        nand_revenue=_number(
            section,
            r"\bNAND\s+flash\s+(?:W\s+)?([0-9][0-9,]*)",
            "nand_revenue",
        ),
        other_products_revenue=_number(
            section,
            r"\bOther\s+products(?:\^\([^)]*\))?\s+(?:W\s+)?([0-9][0-9,]*)",
            "other_products_revenue",
        ),
        total_revenue=_number(
            section,
            r"\bTotal\s+revenue\s+(?:W\s+)?([0-9][0-9,]*)",
            "total_revenue",
        ),
        dram_share_percent=_number(
            text,
            (
                r"Sales\s+of\s+DRAMs\s+accounted\s+for\s+([0-9.]+)%\s+of\s+our\s+"
                r"total\s+revenue\s+in\s+the\s+first\s+quarter\s+of\s+2026"
            ),
            "dram_share_percent",
        ),
        nand_share_percent=_number(
            text,
            (
                r"Sales\s+of\s+NAND\s+flash\s+products\s+accounted\s+for\s+([0-9.]+)%\s+"
                r"of\s+our\s+total\s+revenue\s+in\s+the\s+first\s+quarter\s+of\s+2026"
            ),
            "nand_share_percent",
        ),
    )
    return metrics


def build_sec_product_mix_calibration_evidence(
    spec: SecProductMixCalibrationSpec,
    *,
    observed_date: date,
    submissions_bytes: bytes,
    filing_bytes: bytes,
) -> SecProductMixCalibrationEvidence:
    if spec.filing_date > observed_date:
        raise ValueError("SEC product-mix filing is not yet observable")
    discover_sec_product_mix_filing(spec, submissions_bytes)
    metrics = parse_sec_product_mix_html(spec, filing_bytes)
    dram_implied = metrics.total_revenue * metrics.dram_share_percent / 100.0
    nand_implied = metrics.total_revenue * metrics.nand_share_percent / 100.0
    dram_error = abs(dram_implied - metrics.dram_revenue) / metrics.dram_revenue
    nand_error = abs(nand_implied - metrics.nand_revenue) / metrics.nand_revenue
    calibrated = bool(
        dram_error <= _SHARE_METHOD_RELATIVE_TOLERANCE
        and nand_error <= _SHARE_METHOD_RELATIVE_TOLERANCE
    )
    source_payload = {
        "document_id": spec.document_id,
        "observed_date": observed_date.isoformat(),
        "submissions_sha256": _sha_bytes(submissions_bytes),
        "filing_sha256": _sha_bytes(filing_bytes),
        "metrics": metrics.__dict__,
        "historical_calibration_only": True,
        "current_baseline_eligible": False,
        "q2_allocation_eligible": False,
    }
    evidence_id = _sha_payload(source_payload)
    calibration_payload = {
        "source_evidence_id": evidence_id,
        "method_id": "skhynix_dram_nand_direct_share_v1",
        "method_version": "1.0",
        "dram_share_implied_revenue": dram_implied,
        "nand_share_implied_revenue": nand_implied,
        "dram_share_method_relative_error": dram_error,
        "nand_share_method_relative_error": nand_error,
        "relative_tolerance": _SHARE_METHOD_RELATIVE_TOLERANCE,
        "direct_product_table_reconciled": True,
        "direct_share_method_calibrated": calibrated,
        "other_products_revenue_directly_disclosed": True,
        "share_only_company_reconciliation_eligible": False,
    }
    return SecProductMixCalibrationEvidence(
        evidence_id=evidence_id,
        calibration_evidence_id=_sha_payload(calibration_payload),
        observed_date=observed_date,
        document_id=spec.document_id,
        ticker=spec.ticker,
        issuer_name=spec.issuer_name,
        accession_number=spec.expected_accession_number,
        primary_document=spec.expected_primary_document,
        filing_date=spec.filing_date,
        period_start=spec.period_start,
        period_end=spec.period_end,
        submissions_sha256=_sha_bytes(submissions_bytes),
        filing_sha256=_sha_bytes(filing_bytes),
        metrics=metrics,
        dram_share_implied_revenue=dram_implied,
        nand_share_implied_revenue=nand_implied,
        dram_share_method_relative_error=dram_error,
        nand_share_method_relative_error=nand_error,
        direct_product_table_reconciled=True,
        direct_share_method_calibrated=calibrated,
        other_products_revenue_directly_disclosed=True,
    )


def _evidence_payload(evidence: SecProductMixCalibrationEvidence) -> dict[str, object]:
    return {
        "evidence_id": evidence.evidence_id,
        "calibration_evidence_id": evidence.calibration_evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "document_id": evidence.document_id,
        "ticker": evidence.ticker,
        "issuer_name": evidence.issuer_name,
        "accession_number": evidence.accession_number,
        "primary_document": evidence.primary_document,
        "filing_date": evidence.filing_date.isoformat(),
        "period_start": evidence.period_start.isoformat(),
        "period_end": evidence.period_end.isoformat(),
        "unit": evidence.metrics.unit,
        "total_revenue": evidence.metrics.total_revenue,
        "dram_revenue": evidence.metrics.dram_revenue,
        "nand_revenue": evidence.metrics.nand_revenue,
        "other_products_revenue": evidence.metrics.other_products_revenue,
        "dram_share_percent": evidence.metrics.dram_share_percent,
        "nand_share_percent": evidence.metrics.nand_share_percent,
        "submissions_sha256": evidence.submissions_sha256,
        "filing_sha256": evidence.filing_sha256,
        "dram_share_implied_revenue": evidence.dram_share_implied_revenue,
        "nand_share_implied_revenue": evidence.nand_share_implied_revenue,
        "dram_share_method_relative_error": evidence.dram_share_method_relative_error,
        "nand_share_method_relative_error": evidence.nand_share_method_relative_error,
        "share_method_relative_tolerance": _SHARE_METHOD_RELATIVE_TOLERANCE,
        "direct_product_table_reconciled": True,
        "direct_share_method_calibrated": True,
        "other_products_revenue_directly_disclosed": True,
        "share_only_company_reconciliation_eligible": False,
        "historical_calibration_only": True,
        "current_baseline_eligible": False,
        "q2_allocation_eligible": False,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def capture_sec_product_mix_calibration(
    spec: SecProductMixCalibrationSpec,
    *,
    observed_date: date,
    user_agent: str,
    output: str | Path = DEFAULT_SEC_PRODUCT_MIX_OUTPUT,
    captured_at: datetime | None = None,
    timeout_seconds: float = 20.0,
) -> dict[str, object]:
    submissions_bytes = download_sec_bytes(
        spec.submissions_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    filing_bytes = download_sec_bytes(
        spec.filing_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    evidence = build_sec_product_mix_calibration_evidence(
        spec,
        observed_date=observed_date,
        submissions_bytes=submissions_bytes,
        filing_bytes=filing_bytes,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if captured.date() < observed_date:
        raise ValueError("captured_at cannot precede observed_date")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"SEC product-mix artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        (temporary / "sec_submissions.json").write_bytes(submissions_bytes)
        (temporary / "sec_filing.html").write_bytes(filing_bytes)
        payload = _evidence_payload(evidence)
        (temporary / "calibration.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            **payload,
            "schema_version": 1,
            "status": "sec_product_mix_calibration_captured",
            "captured_at": captured.isoformat(),
            "files": ["sec_submissions.json", "sec_filing.html", "calibration.json"],
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
    pointer = {
        **_evidence_payload(evidence),
        "schema_version": 1,
        "status": "sec_product_mix_calibration_captured",
        "manifest_path": str((directory / "manifest.json").resolve()),
        "calibration_path": str((directory / "calibration.json").resolve()),
        "submissions_path": str((directory / "sec_submissions.json").resolve()),
        "filing_path": str((directory / "sec_filing.html").resolve()),
    }
    pointer_path = root / "latest_sec_product_mix_calibration.json"
    temporary_pointer = root / ".latest_sec_product_mix_calibration.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], payload).items()}


def load_sec_product_mix_calibration_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_SEC_PRODUCT_MIX_REGISTRY,
) -> SecProductMixCalibrationEvidence:
    pointer = _json_object(Path(pointer_path), "SEC product-mix pointer")
    if pointer.get("status") != "sec_product_mix_calibration_captured":
        raise ValueError("SEC product-mix pointer status is invalid")
    observed_date = date.fromisoformat(str(pointer.get("observed_date", "")))
    if observed_date > evaluation_date:
        raise ValueError("SEC product-mix calibration was not yet observed")
    specs = load_sec_product_mix_registry(registry_path)
    document_id = str(pointer.get("document_id", ""))
    if document_id not in specs:
        raise ValueError("SEC product-mix document is not in the checked-in registry")
    spec = specs[document_id]
    submissions_path = Path(str(pointer.get("submissions_path", "")))
    filing_path = Path(str(pointer.get("filing_path", "")))
    try:
        submissions_bytes = submissions_path.read_bytes()
        filing_bytes = filing_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("SEC product-mix archived source bytes are missing") from exc
    reconstructed = build_sec_product_mix_calibration_evidence(
        spec,
        observed_date=observed_date,
        submissions_bytes=submissions_bytes,
        filing_bytes=filing_bytes,
    )
    payload = _json_object(
        Path(str(pointer.get("calibration_path", ""))),
        "SEC product-mix calibration payload",
    )
    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "SEC product-mix calibration manifest",
    )
    expected = _evidence_payload(reconstructed)
    for key, value in expected.items():
        if pointer.get(key) != value or payload.get(key) != value or manifest.get(key) != value:
            raise ValueError(f"SEC product-mix persisted field mismatch: {key}")
    return reconstructed


__all__ = [
    "DEFAULT_SEC_PRODUCT_MIX_OUTPUT",
    "DEFAULT_SEC_PRODUCT_MIX_POINTER",
    "DEFAULT_SEC_PRODUCT_MIX_REGISTRY",
    "SecProductMixCalibrationEvidence",
    "SecProductMixCalibrationSpec",
    "SecProductMixMetrics",
    "build_sec_product_mix_calibration_evidence",
    "capture_sec_product_mix_calibration",
    "discover_sec_product_mix_filing",
    "load_sec_product_mix_calibration_evidence",
    "load_sec_product_mix_registry",
    "parse_sec_product_mix_html",
]
