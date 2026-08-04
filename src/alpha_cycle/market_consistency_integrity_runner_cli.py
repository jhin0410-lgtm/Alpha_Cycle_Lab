"""Run the scope-aware assessment through the integrity-protected raw checker."""

from __future__ import annotations

from alpha_cycle import market_consistency_runner_cli as runner
from alpha_cycle.market_consistency_integrity import run_consistency_check

CHECKER_ATTRIBUTE = "run_consistency_check"


def main(argv: list[str] | None = None) -> int:
    original: object = getattr(runner, CHECKER_ATTRIBUTE)
    setattr(runner, CHECKER_ATTRIBUTE, run_consistency_check)
    try:
        return runner.main(argv)
    finally:
        setattr(runner, CHECKER_ATTRIBUTE, original)


if __name__ == "__main__":
    raise SystemExit(main())
