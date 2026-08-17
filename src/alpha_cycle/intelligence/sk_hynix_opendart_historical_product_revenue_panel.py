"""Batch-capture historical SK hynix direct product revenue from official OpenDART.

Each Q1/Q2/Q3 filing is processed through the same strict source-structure parser,
parser-contract binding, and offline verifier used for the live certification path.
Historical filing layouts may differ. A parser failure is therefore preserved as a
transparent failed period rather than converted into an inferred product allocation.
Only independently replayable successful periods may enter calibration inventory.

When selective resume is requested, an existing period artifact is reused only after its
immutable ZIP/text evidence is replayed non-destructively against the current registered
spec.  Contract rebinding happens only after that replay succeeds.  Invalid or stale
candidates fall through to a normal live OpenDART recapture for that period only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_candidate_replay import (
    replay_periodic_product_revenue_certification_against_spec,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_capture import (
    capture_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    load_periodic_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_contract import (
    bind_periodic_product_revenue_parser_contract,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_HISTORICAL_PRODUCT_REVENUE_REGISTRY = Path(
    "config/skhynix_opendart_historical_product_revenue.yaml"
)
DEFAULT_HISTORICAL_PRODUCT_REVENUE_OUTPUT = Path(
    "data/private/research/skhynix-opendart-historical-product-revenue-panel"
)
DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER = (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_OUTPUT / "latest_historical_product_revenue_panel.json"
)
_KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")
_EXPECTED_PERIODS = (
    "2023Q1",
    "2023Q2",
    "2023Q3",
    "2024Q1",
    "2024Q2",
    "2024Q3",
    "2025Q1",
    "2025Q2",
    "2025Q3",
    "2026Q1",
)
_ALLOWED_ENTRY_STATUSES = frozenset({"certified", "failed"})


def _canonical_hash(payload: object) -> str:
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


def historical_period_id(spec: PeriodicProductRevenueSpec) -> str:
    quarter = (spec.period_end.month - 1) // 3 + 1
    period_id = f"{spec.period_end.year}Q{quarter}"
    expected_start_month = (quarter - 1) * 3 + 1
    if spec.period_start != date(spec.period_end.year, expected_start_month, 1):
        raise ValueError("Historical product-revenue spec is not one direct quarter")
    if spec.period_end.month != quarter * 3:
        raise ValueError("Historical product-revenue spec period end is not quarter-end")
    return period_id


def load_historical_product_revenue_specs(
    path: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_REGISTRY,
) -> tuple[PeriodicProductRevenueSpec, ...]:
    specs = tuple(
        sorted(
            load_periodic_product_revenue_registry(path).values(),
            key=lambda item: (item.period_end, item.document_id),
        )
    )
    periods = tuple(historical_period_id(item) for item in specs)
    if periods != _EXPECTED_PERIODS:
        raise ValueError("Historical product-revenue registry must bind the exact ten periods")
    if len({item.document_id for item in specs}) != len(specs):
        raise ValueError("Historical product-revenue document ids must be unique")
    return specs


@dataclass(frozen=True)
class HistoricalProductRevenuePanelEntry:
    period_id: str
    document_id: str
    status: str
    pointer_path: str | None
    certification_evidence_id: str | None
    chain_evidence_id: str | None
    rcept_no: str | None
    error_type: str | None

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Historical product-revenue panel period is unsupported")
        if self.status not in _ALLOWED_ENTRY_STATUSES:
            raise ValueError("Historical product-revenue panel entry status is invalid")
        if self.status == "certified":
            if not self.pointer_path:
                raise ValueError("Certified historical product revenue requires a pointer")
            hashes = (self.certification_evidence_id, self.chain_evidence_id)
            if any(value is None or not _valid_sha(value) for value in hashes):
                raise ValueError("Certified historical product revenue requires SHA-256 evidence")
            if self.rcept_no is None or len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
                raise ValueError("Certified historical product revenue requires a receipt number")
            if self.error_type is not None:
                raise ValueError("Certified historical product revenue cannot contain an error")
        else:
            if any(
                value is not None
                for value in (
                    self.pointer_path,
                    self.certification_evidence_id,
                    self.chain_evidence_id,
                    self.rcept_no,
                )
            ):
                raise ValueError("Failed historical product revenue cannot claim source evidence")
            if not self.error_type:
                raise ValueError("Failed historical product revenue requires an error type")


@dataclass(frozen=True)
class HistoricalProductRevenuePanelEvidence:
    evidence_id: str
    evaluation_date: date
    ticker: str
    entries: tuple[HistoricalProductRevenuePanelEntry, ...]
    successful_periods: tuple[str, ...]
    failed_periods: tuple[str, ...]
    full_source_coverage_certified: bool
    calibration_support_only: bool = True
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("Historical product-revenue panel evidence_id must be SHA-256")
        if self.ticker != "000660":
            raise ValueError("Historical product-revenue panel supports SK hynix only")
        if tuple(item.period_id for item in self.entries) != _EXPECTED_PERIODS:
            raise ValueError("Historical product-revenue panel entries are not complete/in order")
        successes = tuple(item.period_id for item in self.entries if item.status == "certified")
        failures = tuple(item.period_id for item in self.entries if item.status == "failed")
        if successes != self.successful_periods or failures != self.failed_periods:
            raise ValueError("Historical product-revenue panel status period sets are inconsistent")
        if self.full_source_coverage_certified != (not failures):
            raise ValueError("Historical product-revenue full-coverage flag is inconsistent")
        if (
            not self.calibration_support_only
            or self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Historical product-revenue panel exceeds its trust boundary")


def _stable_evidence_payload(
    *,
    evaluation_date: date,
    entries: tuple[HistoricalProductRevenuePanelEntry, ...],
) -> dict[str, object]:
    return {
        "evaluation_date": evaluation_date.isoformat(),
        "ticker": "000660",
        "entries": [
            {
                "period_id": item.period_id,
                "document_id": item.document_id,
                "status": item.status,
                "certification_evidence_id": item.certification_evidence_id,
                "chain_evidence_id": item.chain_evidence_id,
                "rcept_no": item.rcept_no,
                "error_type": item.error_type,
            }
            for item in entries
        ],
        "calibration_support_only": True,
        "product_profitability_source_fact": False,
    }


def build_historical_product_revenue_panel_evidence(
    *,
    evaluation_date: date,
    entries: tuple[HistoricalProductRevenuePanelEntry, ...],
) -> HistoricalProductRevenuePanelEvidence:
    if tuple(item.period_id for item in entries) != _EXPECTED_PERIODS:
        raise ValueError("Historical product-revenue entries must bind exact ten periods")
    successful = tuple(item.period_id for item in entries if item.status == "certified")
    failed = tuple(item.period_id for item in entries if item.status == "failed")
    return HistoricalProductRevenuePanelEvidence(
        evidence_id=_canonical_hash(
            _stable_evidence_payload(evaluation_date=evaluation_date, entries=entries)
        ),
        evaluation_date=evaluation_date,
        ticker="000660",
        entries=entries,
        successful_periods=successful,
        failed_periods=failed,
        full_source_coverage_certified=not failed,
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


def _certified_entry(
    *,
    period_id: str,
    spec: PeriodicProductRevenueSpec,
    pointer_path: Path,
    evaluation_date: date,
) -> HistoricalProductRevenuePanelEntry:
    # Critical ordering: prove the immutable artifact under the current spec before
    # mutating its parser-contract binding.
    replay_periodic_product_revenue_certification_against_spec(
        pointer_path,
        spec,
        evaluation_date=evaluation_date,
    )
    pointer = bind_periodic_product_revenue_parser_contract(pointer_path, spec)
    certification = load_periodic_product_revenue_certification(
        pointer_path,
        evaluation_date=evaluation_date,
    )
    if certification.period_end != spec.period_end:
        raise ValueError("Historical product-revenue certification period mismatch")
    return HistoricalProductRevenuePanelEntry(
        period_id=period_id,
        document_id=spec.document_id,
        status="certified",
        pointer_path=str(pointer_path.resolve()),
        certification_evidence_id=certification.evidence_id,
        chain_evidence_id=str(pointer.get("chain_evidence_id", "")),
        rcept_no=certification.rcept_no,
        error_type=None,
    )


def capture_historical_product_revenue_panel(
    client: OpenDartReadOnlyClient,
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_REGISTRY,
    output: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_OUTPUT,
    captured_at: datetime | None = None,
    resume_valid_existing: bool = False,
) -> dict[str, object]:
    """Capture ten periods, optionally reusing only current-spec replayable artifacts."""

    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if captured.astimezone(_KOREA_TIME_ZONE).date() < evaluation_date:
        raise ValueError("captured_at cannot precede evaluation_date in Asia/Seoul")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    entries: list[HistoricalProductRevenuePanelEntry] = []
    reused_periods: list[str] = []
    capture_attempted_periods: list[str] = []
    reuse_rejected_periods: list[str] = []
    reuse_rejected_error_types: dict[str, str] = {}

    for spec in load_historical_product_revenue_specs(registry_path):
        period_id = historical_period_id(spec)
        period_output = root / period_id
        pointer_path = period_output / "latest_certification.json"

        if resume_valid_existing and pointer_path.is_file():
            try:
                entries.append(
                    _certified_entry(
                        period_id=period_id,
                        spec=spec,
                        pointer_path=pointer_path,
                        evaluation_date=evaluation_date,
                    )
                )
                reused_periods.append(period_id)
                continue
            except Exception as exc:
                reuse_rejected_periods.append(period_id)
                reuse_rejected_error_types[period_id] = type(exc).__name__

        capture_attempted_periods.append(period_id)
        try:
            capture_periodic_product_revenue_certification(
                client,
                spec,
                evaluation_date=evaluation_date,
                output=period_output,
                captured_at=captured,
            )
            entries.append(
                _certified_entry(
                    period_id=period_id,
                    spec=spec,
                    pointer_path=pointer_path,
                    evaluation_date=evaluation_date,
                )
            )
        except Exception as exc:
            entries.append(
                HistoricalProductRevenuePanelEntry(
                    period_id=period_id,
                    document_id=spec.document_id,
                    status="failed",
                    pointer_path=None,
                    certification_evidence_id=None,
                    chain_evidence_id=None,
                    rcept_no=None,
                    error_type=type(exc).__name__,
                )
            )

    evidence = build_historical_product_revenue_panel_evidence(
        evaluation_date=evaluation_date,
        entries=tuple(entries),
    )
    payload = {
        **asdict(evidence),
        "evaluation_date": evidence.evaluation_date.isoformat(),
        "entries": [asdict(item) for item in evidence.entries],
    }
    panel_path = root / "historical_product_revenue_panel.json"
    panel_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    pointer = {
        **payload,
        "schema_version": 1,
        "status": "skhynix_opendart_historical_product_revenue_panel_captured",
        "panel_path": str(panel_path.resolve()),
        "registry_path": str(Path(registry_path).resolve()),
        "resume_valid_existing": resume_valid_existing,
        "reused_periods": reused_periods,
        "capture_attempted_periods": capture_attempted_periods,
        "reuse_rejected_periods": reuse_rejected_periods,
        "reuse_rejected_error_types": reuse_rejected_error_types,
    }
    pointer_path = root / "latest_historical_product_revenue_panel.json"
    temporary = root / ".latest_historical_product_revenue_panel.json.tmp"
    temporary.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(pointer_path)
    return pointer


__all__ = [
    "DEFAULT_HISTORICAL_PRODUCT_REVENUE_OUTPUT",
    "DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER",
    "DEFAULT_HISTORICAL_PRODUCT_REVENUE_REGISTRY",
    "HistoricalProductRevenuePanelEntry",
    "HistoricalProductRevenuePanelEvidence",
    "build_historical_product_revenue_panel_evidence",
    "capture_historical_product_revenue_panel",
    "historical_period_id",
    "load_historical_product_revenue_specs",
]
