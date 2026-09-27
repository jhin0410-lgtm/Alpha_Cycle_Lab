from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_product_profitability_magnitude_descriptor_diagnostic import (
    DEFAULT_MAGNITUDE_DESCRIPTOR_DIAGNOSTIC_OUTPUT,
    capture_magnitude_descriptor_diagnostic,
    load_magnitude_descriptor_diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    DEFAULT_STRUCTURAL_RANK_PROBE_POINTER,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory literal magnitude syntax in the verified SK hynix structural "
            "rank-probe rows without assigning numeric model inputs or opening fit gates."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--rank-probe-pointer",
        default=str(DEFAULT_STRUCTURAL_RANK_PROBE_POINTER),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_MAGNITUDE_DESCRIPTOR_DIAGNOSTIC_OUTPUT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = Path(args.output)
    captured = capture_magnitude_descriptor_diagnostic(
        evaluation_date=args.evaluation_date,
        rank_probe_pointer=Path(args.rank_probe_pointer),
        output=output,
    )
    verified = load_magnitude_descriptor_diagnostic(
        output / "latest_magnitude_descriptor_diagnostic.json",
        evaluation_date=args.evaluation_date,
    )
    summary = {
        "status": captured["status"],
        "evidence_id": verified.evidence_id,
        "source_rank_probe_evidence_id": verified.source_rank_probe_evidence_id,
        "source_rank_probe_pointer_sha256": verified.source_rank_probe_pointer_sha256,
        "method_id": verified.method_id,
        "method_version": verified.method_version,
        "training_periods": verified.training_periods,
        "observation_count": verified.observation_count,
        "unique_source_text_count": verified.unique_source_text_count,
        "descriptor_kind_counts": dict(verified.descriptor_kind_counts),
        "numeric_token_observation_count": verified.numeric_token_observation_count,
        "unclassified_source_texts": verified.unclassified_source_texts,
        "rank_probe_ready": verified.rank_probe_ready,
        "all_descriptors_classified": verified.all_descriptors_classified,
        "measurement_error_encoding_registered": (
            verified.measurement_error_encoding_registered
        ),
        "numeric_driver_source_facts_available": (
            verified.numeric_driver_source_facts_available
        ),
        "model_numeric_values_assigned": verified.model_numeric_values_assigned,
        "estimation_inputs_ready": verified.estimation_inputs_ready,
        "fit_attempt_allowed": verified.fit_attempt_allowed,
        "holdout_evaluation_allowed": verified.holdout_evaluation_allowed,
        "block_reason": verified.block_reason,
        "product_profitability_source_fact": verified.product_profitability_source_fact,
        "numeric_forecast_enabled": verified.numeric_forecast_enabled,
        "fair_value_estimate_enabled": verified.fair_value_estimate_enabled,
        "target_price_enabled": verified.target_price_enabled,
        "decision_score_enabled": verified.decision_score_enabled,
        "artifact_directory": captured["artifact_directory"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
