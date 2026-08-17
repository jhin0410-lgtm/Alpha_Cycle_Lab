"""Archive and offline-replay the SK hynix profitability promotion-readiness audit."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_product_profitability_promotion_readiness import (
    DEFAULT_PROMOTION_READINESS_OUTPUT,
    DEFAULT_PROMOTION_READINESS_POLICY,
    PromotionReadinessResult,
    load_promotion_readiness_from_rank_probe,
    promotion_readiness_payload,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    DEFAULT_STRUCTURAL_METHOD_PATH,
)


def capture_promotion_readiness_report(
    *,
    evaluation_date: date,
    rank_probe_pointer: str | Path,
    policy_path: str | Path = DEFAULT_PROMOTION_READINESS_POLICY,
    method_path: str | Path = DEFAULT_STRUCTURAL_METHOD_PATH,
    output: str | Path = DEFAULT_PROMOTION_READINESS_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    result = load_promotion_readiness_from_rank_probe(
        evaluation_date=evaluation_date,
        rank_probe_pointer=rank_probe_pointer,
        policy_path=policy_path,
        method_path=method_path,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("Promotion-readiness captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + result.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Promotion-readiness artifact already exists: {directory}")
    directory.mkdir()
    report = promotion_readiness_payload(result)
    report_path = directory / "promotion_readiness.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    pointer = {
        **report,
        "schema_version": 1,
        "status": "skhynix_product_profitability_promotion_readiness_captured",
        "captured_at": captured.isoformat(),
        "report_path": str(report_path.resolve()),
        "rank_probe_pointer": str(Path(rank_probe_pointer).resolve()),
        "policy_path": str(Path(policy_path).resolve()),
        "method_path": str(Path(method_path).resolve()),
    }
    pointer_path = root / "latest_promotion_readiness.json"
    temporary = root / ".latest_promotion_readiness.json.tmp"
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


def load_promotion_readiness_report(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> PromotionReadinessResult:
    pointer = _object(Path(pointer_path), "Promotion-readiness pointer")
    if pointer.get("status") != "skhynix_product_profitability_promotion_readiness_captured":
        raise ValueError("Promotion-readiness pointer status is invalid")
    if date.fromisoformat(str(pointer.get("evaluation_date", ""))) != evaluation_date:
        raise ValueError("Promotion-readiness evaluation date mismatch")
    reconstructed = load_promotion_readiness_from_rank_probe(
        evaluation_date=evaluation_date,
        rank_probe_pointer=Path(str(pointer.get("rank_probe_pointer", ""))),
        policy_path=Path(str(pointer.get("policy_path", ""))),
        method_path=Path(str(pointer.get("method_path", ""))),
    )
    expected = promotion_readiness_payload(reconstructed)
    for key, value in expected.items():
        if pointer.get(key) != value:
            raise ValueError(f"Promotion-readiness pointer no longer reproduces: {key}")
    report = _object(Path(str(pointer.get("report_path", ""))), "Promotion-readiness report")
    if report != expected:
        raise ValueError("Promotion-readiness report payload no longer reproduces")
    return reconstructed


__all__ = [
    "capture_promotion_readiness_report",
    "load_promotion_readiness_report",
]
