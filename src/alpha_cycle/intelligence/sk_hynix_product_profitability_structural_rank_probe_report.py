"""Archive and offline-replay the SK hynix structural profitability rank probe."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    DEFAULT_STRUCTURAL_METHOD_PATH,
    DEFAULT_STRUCTURAL_RANK_PROBE_OUTPUT,
    StructuralRankProbeResult,
    load_structural_rank_probe_from_pointers,
)


def structural_rank_probe_payload(result: StructuralRankProbeResult) -> dict[str, object]:
    payload = asdict(result)
    payload["evaluation_date"] = result.evaluation_date.isoformat()
    payload["rows"] = [asdict(item) for item in result.rows]
    return payload


def capture_structural_rank_probe_report(
    *,
    evaluation_date: date,
    method_path: str | Path = DEFAULT_STRUCTURAL_METHOD_PATH,
    historical_product_revenue_pointer: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
    company_profitability_pointer: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
    cycle_driver_pointer: str | Path = DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
    output: str | Path = DEFAULT_STRUCTURAL_RANK_PROBE_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """Replay all inputs and persist a deterministic rank-only diagnostic report."""

    result = load_structural_rank_probe_from_pointers(
        evaluation_date=evaluation_date,
        method_path=method_path,
        historical_product_revenue_pointer=historical_product_revenue_pointer,
        company_profitability_pointer=company_profitability_pointer,
        cycle_driver_pointer=cycle_driver_pointer,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("Structural rank-probe captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + result.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Structural rank-probe artifact already exists: {directory}")
    directory.mkdir()

    report_path = directory / "rank_probe.json"
    report = structural_rank_probe_payload(result)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    pointer = {
        **report,
        "schema_version": 1,
        "status": "skhynix_product_profitability_structural_rank_probe_captured",
        "captured_at": captured.isoformat(),
        "report_path": str(report_path.resolve()),
        "method_path": str(Path(method_path).resolve()),
        "historical_product_revenue_pointer": str(
            Path(historical_product_revenue_pointer).resolve()
        ),
        "company_profitability_pointer": str(Path(company_profitability_pointer).resolve()),
        "cycle_driver_pointer": str(Path(cycle_driver_pointer).resolve()),
    }
    pointer_path = root / "latest_structural_rank_probe.json"
    temporary = root / ".latest_structural_rank_probe.json.tmp"
    temporary.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


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


def load_structural_rank_probe_report(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> StructuralRankProbeResult:
    """Recompute a persisted rank probe from the bound evidence pointers and method."""

    pointer = _object(Path(pointer_path), "Structural rank-probe pointer")
    if pointer.get("status") != "skhynix_product_profitability_structural_rank_probe_captured":
        raise ValueError("Structural rank-probe pointer status is invalid")
    if date.fromisoformat(str(pointer.get("evaluation_date", ""))) != evaluation_date:
        raise ValueError("Structural rank-probe evaluation date mismatch")

    reconstructed = load_structural_rank_probe_from_pointers(
        evaluation_date=evaluation_date,
        method_path=Path(str(pointer.get("method_path", ""))),
        historical_product_revenue_pointer=Path(
            str(pointer.get("historical_product_revenue_pointer", ""))
        ),
        company_profitability_pointer=Path(
            str(pointer.get("company_profitability_pointer", ""))
        ),
        cycle_driver_pointer=Path(str(pointer.get("cycle_driver_pointer", ""))),
    )
    expected = structural_rank_probe_payload(reconstructed)
    for key, value in expected.items():
        if pointer.get(key) != value:
            raise ValueError(f"Structural rank-probe pointer no longer reproduces: {key}")

    report = _object(Path(str(pointer.get("report_path", ""))), "Structural rank-probe report")
    if report != expected:
        raise ValueError("Structural rank-probe report payload no longer reproduces")
    return reconstructed


__all__ = [
    "capture_structural_rank_probe_report",
    "load_structural_rank_probe_report",
    "structural_rank_probe_payload",
]
