"""Run the scope-aware assessment through integrity-protected functions."""

from __future__ import annotations

from alpha_cycle import market_consistency_runner_cli as runner
from alpha_cycle.adjusted_market_consistency_compat import (
    adjusted_market_consistency_runtime,
)
from alpha_cycle.market_consistency_assessment_integrity import (
    assess_consistency_result,
)
from alpha_cycle.market_consistency_integrity import (
    _atomic_json,
    run_consistency_check,
)

CHECKER_ATTRIBUTE = "run_consistency_check"
ASSESSOR_ATTRIBUTE = "assess_consistency_result"
ATOMIC_JSON_ATTRIBUTE = "_atomic_json"


def main(argv: list[str] | None = None) -> int:
    original_checker: object = getattr(runner, CHECKER_ATTRIBUTE)
    original_assessor: object = getattr(runner, ASSESSOR_ATTRIBUTE)
    original_atomic_json: object = getattr(runner, ATOMIC_JSON_ATTRIBUTE)
    setattr(runner, CHECKER_ATTRIBUTE, run_consistency_check)
    setattr(runner, ASSESSOR_ATTRIBUTE, assess_consistency_result)
    setattr(runner, ATOMIC_JSON_ATTRIBUTE, _atomic_json)
    try:
        with adjusted_market_consistency_runtime():
            return runner.main(argv)
    finally:
        setattr(runner, CHECKER_ATTRIBUTE, original_checker)
        setattr(runner, ASSESSOR_ATTRIBUTE, original_assessor)
        setattr(runner, ATOMIC_JSON_ATTRIBUTE, original_atomic_json)


if __name__ == "__main__":
    raise SystemExit(main())
