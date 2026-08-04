"""Run the scope-aware assessment through integrity-protected functions."""

from __future__ import annotations

from alpha_cycle import market_consistency_runner_cli as runner
from alpha_cycle.market_consistency_assessment_integrity import (
    assess_consistency_result,
)
from alpha_cycle.market_consistency_integrity import run_consistency_check

CHECKER_ATTRIBUTE = "run_consistency_check"
ASSESSOR_ATTRIBUTE = "assess_consistency_result"


def main(argv: list[str] | None = None) -> int:
    original_checker: object = getattr(runner, CHECKER_ATTRIBUTE)
    original_assessor: object = getattr(runner, ASSESSOR_ATTRIBUTE)
    setattr(runner, CHECKER_ATTRIBUTE, run_consistency_check)
    setattr(runner, ASSESSOR_ATTRIBUTE, assess_consistency_result)
    try:
        return runner.main(argv)
    finally:
        setattr(runner, CHECKER_ATTRIBUTE, original_checker)
        setattr(runner, ASSESSOR_ATTRIBUTE, original_assessor)


if __name__ == "__main__":
    raise SystemExit(main())
