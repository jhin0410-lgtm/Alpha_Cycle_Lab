from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_layout_profile import (
    HistoricalExpansionLayoutContext,
    HistoricalExpansionLayoutProfile,
    profile_historical_expansion_failures,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
)

DEFAULT_LAYOUT_PROFILE_OUTPUT = Path(
    "data/private/research/skhynix-profitability-historical-expansion-layout-profile"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fingerprint preserved 2021-2022 SK hynix OpenDART parser failures without "
            "extracting revenue or promoting evidence."
        )
    )
    parser.add_argument("--probe-output", default=str(DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT))
    parser.add_argument("--output", default=str(DEFAULT_LAYOUT_PROFILE_OUTPUT))
    return parser


def _interesting_lines(context: HistoricalExpansionLayoutContext) -> tuple[str, ...]:
    terms = ("dram", "nand", "3개월", "누적", "백만원", "억원", "매출액", "제품", "상품")
    selected: list[str] = []
    for line in context.lines:
        folded = line.casefold()
        compact = line.replace(" ", "")
        amount_like = compact.replace(",", "").replace(".", "").strip("()-").isdigit()
        if any(term in folded for term in terms) or amount_like:
            selected.append(line)
        if len(selected) >= 14:
            break
    return tuple(selected)


def _summary(profile: HistoricalExpansionLayoutProfile) -> dict[str, object]:
    return {
        "period_id": profile.period_id,
        "evidence_id": profile.evidence_id,
        "rcept_no": profile.rcept_no,
        "report_name": profile.report_name,
        "line_count": profile.line_count,
        "nonempty_line_count": profile.nonempty_line_count,
        "signal_counts": dict(profile.signal_counts),
        "context_count": profile.context_count,
        "context_previews": [
            {
                "start_line": context.start_line,
                "end_line": context.end_line,
                "trigger_terms": context.trigger_terms,
                "amount_token_count": context.amount_token_count,
                "has_three_month_marker": context.has_three_month_marker,
                "has_cumulative_marker": context.has_cumulative_marker,
                "unit_markers": context.unit_markers,
                "interesting_lines": _interesting_lines(context),
            }
            for context in profile.contexts[:6]
        ],
        "archive_member_count": profile.archive_member_count,
        "archive_member_suffix_counts": dict(profile.archive_member_suffix_counts),
        "archive_member_sample": profile.archive_member_sample,
        "parser_family_inferred": profile.parser_family_inferred,
        "product_revenue_extracted": profile.product_revenue_extracted,
        "source_certification_promoted": profile.source_certification_promoted,
        "training_row_promoted": profile.training_row_promoted,
        "fit_enabled": profile.fit_enabled,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    profiles = profile_historical_expansion_failures(output=Path(args.probe_output))
    captured_at = datetime.now(UTC)
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    report_path = root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__layout_profiles.json"
    )
    report = {
        "status": "skhynix_historical_expansion_layout_profile_completed",
        "captured_at": captured_at.isoformat(),
        "profile_count": len(profiles),
        "profiles": [asdict(profile) for profile in profiles],
        "parser_family_inferred": False,
        "product_revenue_extracted": False,
        "frontier_promoted": False,
        "fit_enabled": False,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = {
        "status": report["status"],
        "profile_count": len(profiles),
        "periods": tuple(profile.period_id for profile in profiles),
        "profiles": [_summary(profile) for profile in profiles],
        "report_path": str(report_path.resolve()),
        "parser_family_inferred": False,
        "product_revenue_extracted": False,
        "frontier_promoted": False,
        "fit_enabled": False,
        "next_action": "design_parser_family_only_after_reviewing_preserved_layout_profiles",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
