"""Historical SK hynix DRAM/NAND cycle-driver support from archived SEC filing bytes.

The official SK hynix SEC 424B4 discloses quarter-over-quarter qualitative bands for
DRAM/NAND bit sales volume and U.S.-dollar average selling price.  This module preserves
those issuer-reported bands verbatim after whitespace normalization.  It deliberately
does not map expressions such as ``Mid-60% Increase`` to a point estimate, and it cannot
promote the evidence into a numeric forecast, valuation, target price, or decision score.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.sec_product_profitability_support import (
    DEFAULT_SEC_PRODUCT_PROFITABILITY_POINTER,
)
from alpha_cycle.intelligence.sec_product_profitability_support_verifier import (
    load_sec_product_profitability_support_evidence,
)

DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_OUTPUT = Path(
    "data/private/research/sec-product-cycle-driver-support"
)
DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER = (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_OUTPUT / "latest_sec_product_cycle_driver_support.json"
)
_KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")
_EXPECTED_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year, quarters in ((2023, 4), (2024, 4), (2025, 4), (2026, 1))
    for quarter in range(1, quarters + 1)
)
_DRIVER_ROW_LABELS = (
    "DRAM Bit Sales Volume",
    "DRAM Average Selling Price",
    "NAND Flash Bit Sales Volume",
    "NAND Flash Average Selling Price",
)


def _normalize(value: str) -> str:
    return " ".join(
        value.replace("\u00a0", " ")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .split()
    )


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


class _HtmlRowsParser(HTMLParser):
    """Keep table-row/cell structure without adding an HTML dependency."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, ...]] = []
        self._row_depth = 0
        self._cell_depth = 0
        self._cells: list[str] = []
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.casefold()
        if lowered == "tr":
            self._row_depth += 1
            if self._row_depth == 1:
                self._cells = []
        elif lowered in {"td", "th"} and self._row_depth > 0:
            self._cell_depth += 1
            if self._cell_depth == 1:
                self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"td", "th"} and self._cell_depth > 0:
            if self._cell_depth == 1:
                value = _normalize(" ".join(self._cell_parts))
                if value:
                    self._cells.append(value)
                self._cell_parts = []
            self._cell_depth -= 1
        elif lowered == "tr" and self._row_depth > 0:
            if self._row_depth == 1 and self._cells:
                self.rows.append(tuple(self._cells))
                self._cells = []
            self._row_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._row_depth > 0 and self._cell_depth > 0 and data.strip():
            self._cell_parts.append(data)


def extract_html_rows(filing_bytes: bytes) -> tuple[tuple[str, ...], ...]:
    parser = _HtmlRowsParser()
    parser.feed(filing_bytes.decode("utf-8", errors="replace"))
    parser.close()
    return tuple(parser.rows)


def _period_id(cell: str) -> str | None:
    compact = _normalize(cell).replace(" ", "")
    if len(compact) != 6 or compact[1] != "Q":
        return None
    quarter = compact[0]
    year = compact[2:]
    if quarter not in "1234" or len(year) != 4 or not year.isdigit():
        return None
    return f"{year}Q{quarter}"


def _find_period_sequence(rows: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    candidates: list[tuple[str, ...]] = []
    for row in rows:
        periods = tuple(period for cell in row if (period := _period_id(cell)) is not None)
        if periods == _EXPECTED_PERIODS:
            candidates.append(periods)
    unique = tuple(dict.fromkeys(candidates))
    if len(unique) != 1:
        raise ValueError(
            "SEC product cycle-driver quarter header must resolve to one exact 13-quarter sequence"
        )
    return unique[0]


def _find_driver_values(
    rows: tuple[tuple[str, ...], ...],
    label: str,
) -> tuple[str, ...]:
    candidates: list[tuple[str, ...]] = []
    target = label.casefold()
    for row in rows:
        normalized = tuple(_normalize(cell) for cell in row)
        indices = [index for index, cell in enumerate(normalized) if cell.casefold() == target]
        if len(indices) != 1:
            continue
        values = tuple(item for item in normalized[indices[0] + 1 :] if item)
        if len(values) == len(_EXPECTED_PERIODS):
            candidates.append(values)
    unique = tuple(dict.fromkeys(candidates))
    if len(unique) != 1:
        raise ValueError(
            f"SEC product cycle-driver row must resolve uniquely with 13 values: {label}"
        )
    values = unique[0]
    for value in values:
        if value != "Flat" and not value.endswith((" Increase", " Decrease")):
            raise ValueError(f"SEC product cycle-driver band is not preserved text: {value}")
    return values


@dataclass(frozen=True)
class QuarterlyProductCycleDriverObservation:
    period_id: str
    dram_bit_sales_volume_qoq_text: str
    dram_asp_usd_qoq_text: str
    nand_bit_sales_volume_qoq_text: str
    nand_asp_usd_qoq_text: str

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("SEC product cycle-driver period is unsupported")
        values = (
            self.dram_bit_sales_volume_qoq_text,
            self.dram_asp_usd_qoq_text,
            self.nand_bit_sales_volume_qoq_text,
            self.nand_asp_usd_qoq_text,
        )
        if any(not _normalize(item) for item in values):
            raise ValueError("SEC product cycle-driver source bands cannot be blank")


@dataclass(frozen=True)
class SecProductCycleDriverSupportEvidence:
    evidence_id: str
    observed_date: date
    ticker: str
    accession_number: str
    source_profitability_support_evidence_id: str
    source_filing_sha256: str
    observations: tuple[QuarterlyProductCycleDriverObservation, ...]
    observation_count: int
    textual_band_source_facts: bool = True
    numeric_driver_values_available: bool = False
    calibration_support_only: bool = True
    current_baseline_eligible: bool = False
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.source_profitability_support_evidence_id,
            self.source_filing_sha256,
        )
        if any(not _valid_sha(item) for item in hashes):
            raise ValueError("SEC product cycle-driver evidence hashes must be SHA-256")
        if self.ticker != "000660":
            raise ValueError("SEC product cycle-driver support v1 supports SK hynix only")
        periods = tuple(item.period_id for item in self.observations)
        if periods != _EXPECTED_PERIODS or self.observation_count != len(self.observations):
            raise ValueError("SEC product cycle-driver evidence must contain all 13 bound quarters")
        if (
            not self.textual_band_source_facts
            or self.numeric_driver_values_available
            or not self.calibration_support_only
            or self.current_baseline_eligible
            or self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SEC product cycle-driver evidence exceeds its trust boundary")


def parse_sec_product_cycle_driver_html(
    filing_bytes: bytes,
) -> tuple[QuarterlyProductCycleDriverObservation, ...]:
    rows = extract_html_rows(filing_bytes)
    if not rows:
        raise ValueError("SEC product cycle-driver filing has no table rows")
    periods = _find_period_sequence(rows)
    values = {
        label: _find_driver_values(rows, label)
        for label in _DRIVER_ROW_LABELS
    }
    return tuple(
        QuarterlyProductCycleDriverObservation(
            period_id=period,
            dram_bit_sales_volume_qoq_text=values["DRAM Bit Sales Volume"][index],
            dram_asp_usd_qoq_text=values["DRAM Average Selling Price"][index],
            nand_bit_sales_volume_qoq_text=values["NAND Flash Bit Sales Volume"][index],
            nand_asp_usd_qoq_text=values["NAND Flash Average Selling Price"][index],
        )
        for index, period in enumerate(periods)
    )


def build_sec_product_cycle_driver_support_evidence(
    *,
    observed_date: date,
    ticker: str,
    accession_number: str,
    source_profitability_support_evidence_id: str,
    expected_filing_sha256: str,
    filing_bytes: bytes,
) -> SecProductCycleDriverSupportEvidence:
    if ticker != "000660":
        raise ValueError("SEC product cycle-driver source binding must be SK hynix")
    filing_sha256 = _sha_bytes(filing_bytes)
    if filing_sha256 != expected_filing_sha256:
        raise ValueError("SEC product cycle-driver archived filing hash does not match source support")
    observations = parse_sec_product_cycle_driver_html(filing_bytes)
    payload = {
        "observed_date": observed_date.isoformat(),
        "ticker": ticker,
        "accession_number": accession_number,
        "source_profitability_support_evidence_id": source_profitability_support_evidence_id,
        "source_filing_sha256": filing_sha256,
        "observations": [asdict(item) for item in observations],
        "textual_band_source_facts": True,
        "numeric_driver_values_available": False,
        "calibration_support_only": True,
    }
    return SecProductCycleDriverSupportEvidence(
        evidence_id=_sha_payload(payload),
        observed_date=observed_date,
        ticker=ticker,
        accession_number=accession_number,
        source_profitability_support_evidence_id=source_profitability_support_evidence_id,
        source_filing_sha256=filing_sha256,
        observations=observations,
        observation_count=len(observations),
    )


def _object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _evidence_payload(evidence: SecProductCycleDriverSupportEvidence) -> dict[str, object]:
    return {
        "evidence_id": evidence.evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "ticker": evidence.ticker,
        "accession_number": evidence.accession_number,
        "source_profitability_support_evidence_id": (
            evidence.source_profitability_support_evidence_id
        ),
        "source_filing_sha256": evidence.source_filing_sha256,
        "observations": [asdict(item) for item in evidence.observations],
        "observation_count": evidence.observation_count,
        "textual_band_source_facts": True,
        "numeric_driver_values_available": False,
        "calibration_support_only": True,
        "current_baseline_eligible": False,
        "product_profitability_source_fact": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }


def capture_sec_product_cycle_driver_support(
    *,
    profitability_support_pointer: str | Path = DEFAULT_SEC_PRODUCT_PROFITABILITY_POINTER,
    evaluation_date: date,
    output: str | Path = DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    source_pointer_path = Path(profitability_support_pointer)
    support = load_sec_product_profitability_support_evidence(
        source_pointer_path,
        evaluation_date=evaluation_date,
    )
    source_pointer = _object(source_pointer_path, "SEC product-profitability pointer")
    filing_path = Path(str(source_pointer.get("filing_path", "")))
    try:
        filing_bytes = filing_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("SEC product cycle-driver source filing bytes are missing") from exc
    evidence = build_sec_product_cycle_driver_support_evidence(
        observed_date=support.observed_date,
        ticker=support.ticker,
        accession_number=support.accession_number,
        source_profitability_support_evidence_id=support.evidence_id,
        expected_filing_sha256=support.filing_sha256,
        filing_bytes=filing_bytes,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if captured.astimezone(_KOREA_TIME_ZONE).date() < evidence.observed_date:
        raise ValueError("captured_at cannot precede source observed_date in Asia/Seoul")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"SEC product cycle-driver artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        payload = _evidence_payload(evidence)
        (temporary / "cycle_driver_support.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            **payload,
            "schema_version": 1,
            "status": "sec_product_cycle_driver_support_captured",
            "captured_at": captured.isoformat(),
            "source_profitability_support_pointer": str(source_pointer_path.resolve()),
            "source_filing_path": str(filing_path.resolve()),
            "files": ["cycle_driver_support.json"],
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
        "status": "sec_product_cycle_driver_support_captured",
        "manifest_path": str((directory / "manifest.json").resolve()),
        "support_path": str((directory / "cycle_driver_support.json").resolve()),
        "source_profitability_support_pointer": str(source_pointer_path.resolve()),
        "source_filing_path": str(filing_path.resolve()),
    }
    pointer_path = root / "latest_sec_product_cycle_driver_support.json"
    temporary_pointer = root / ".latest_sec_product_cycle_driver_support.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


__all__ = [
    "DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_OUTPUT",
    "DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER",
    "QuarterlyProductCycleDriverObservation",
    "SecProductCycleDriverSupportEvidence",
    "build_sec_product_cycle_driver_support_evidence",
    "capture_sec_product_cycle_driver_support",
    "extract_html_rows",
    "parse_sec_product_cycle_driver_html",
]
