"""CLI diagnostics for the latest Kiwoom investor-flow evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from alpha_cycle.intelligence.investor_flow_evidence import (
    InvestorFlowEvidence,
    load_investor_flow_evidence,
)

DEFAULT_POINTER = Path(
    "data/private/live-research/kiwoom-openapi-plus-investor-flow/"
    "latest_investor_flow_export.json"
)


def _evaluation_date_from_pointer(pointer_path: Path) -> datetime:
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if not isinstance(pointer, dict):
        raise ValueError(f"expected JSON object: {pointer_path}")
    manifest_path = Path(str(pointer.get("manifest_path", "")))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"expected JSON object: {manifest_path}")
    reference_date = str(manifest.get("reference_date", ""))
    try:
        return datetime.strptime(reference_date, "%Y%m%d")
    except ValueError as exc:
        raise ValueError("investor-flow manifest reference_date must use YYYYMMDD") from exc


def build_report(pointer_path: Path = DEFAULT_POINTER) -> InvestorFlowEvidence:
    """Compatibility wrapper used by tests and the human-readable CLI."""

    evaluation = _evaluation_date_from_pointer(pointer_path)
    return load_investor_flow_evidence(
        pointer_path,
        evaluation_date=evaluation.date(),
    )


def _print_report(report: InvestorFlowEvidence) -> None:
    print("KIWOOM INVESTOR FLOW LIVE DIAGNOSTICS")
    print(f"snapshot: {report.snapshot_id}")
    print(f"request contract: {report.request_contract_status}")
    print(f"provider raw semantic status: {report.provider_semantic_status}")
    print(f"field mapping verified: {str(report.field_mapping_verified).lower()}")
    print(f"point in time verified: {str(report.point_in_time_verified).lower()}")
    print(f"evidence verified: {str(report.evidence_verified).lower()}")
    print("decision score: disabled")
    print()
    for diag in report.tickers:
        print(
            f"{diag.ticker}: rows={diag.row_count} "
            f"date_desc={str(diag.date_order_descending).lower()} "
            f"price_rows={diag.positive_normalized_price_rows}/{diag.row_count} "
            f"market_balance_exact={diag.exact_market_balance_rows}/"
            f"{diag.comparable_market_balance_rows} "
            f"market_balance_max_abs={diag.max_abs_market_balance_residual_shares} "
            f"institution_breakdown_exact={diag.exact_institution_breakdown_rows}/"
            f"{diag.comparable_institution_breakdown_rows} "
            f"institution_breakdown_max_abs={diag.max_abs_institution_breakdown_residual_shares} "
            f"asof_rows={diag.rows_on_or_before_evaluation_date}/{diag.row_count}"
        )
    print()
    for row in report.windows:
        return_text = (
            "n/a" if row.price_return_pct is None else f"{row.price_return_pct:.2f}%"
        )
        ratio_text = (
            "n/a"
            if row.foreign_institution_volume_ratio is None
            else f"{row.foreign_institution_volume_ratio * 100.0:.2f}%"
        )
        state = row.descriptive_state if report.evidence_verified else "unverified"
        print(
            f"{row.ticker} {row.window}d: price={return_text} "
            f"foreign={row.foreign_net_buy_shares} "
            f"institution={row.institution_net_buy_shares} "
            f"foreign+institution={row.foreign_institution_net_buy_shares} "
            f"flow/volume={ratio_text} state={state}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and summarize the latest unscored Kiwoom investor-flow artifact"
    )
    parser.add_argument("--pointer", type=Path, default=DEFAULT_POINTER)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.pointer)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"KIWOOM INVESTOR FLOW LIVE DIAGNOSTICS: FAIL: {exc}")
        return 2
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
