"""Strategy boundary: strategies emit targets and cannot access a broker."""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

from alpha_cycle.domain.models import TargetPosition


class Strategy(Protocol):
    """Target-generating research strategy."""

    def generate_targets(
        self, event_date: date, history: pd.DataFrame
    ) -> list[TargetPosition] | None:
        """Return targets when rebalancing, otherwise None."""
        ...

