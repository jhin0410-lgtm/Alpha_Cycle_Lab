"""Deterministic example strategies for engine validation, not investment advice."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from alpha_cycle.domain.models import TargetPosition


@dataclass
class BuyAndHoldStrategy:
    """Buy selected tickers once at equal weights."""

    tickers: list[str] | None = None
    invested: bool = field(default=False, init=False)

    def generate_targets(
        self, event_date: date, history: pd.DataFrame
    ) -> list[TargetPosition] | None:
        """Emit a single equal-weight allocation."""
        del event_date
        if self.invested:
            return None
        available = sorted(history.loc[history["date"] == history["date"].max(), "ticker"].unique())
        selected = [ticker for ticker in (self.tickers or available) if ticker in available]
        if not selected:
            return None
        self.invested = True
        weight = 1.0 / len(selected)
        return [TargetPosition(ticker, weight) for ticker in selected]


@dataclass
class CrossSectionalMomentumStrategy:
    """Top-K trailing-return example with periodic equal/score weighting."""

    lookback: int = 20
    top_k: int = 5
    rebalance_every: int = 21
    weighting: str = "equal"
    minimum_trading_value: float = 0.0
    _seen_dates: list[date] = field(default_factory=list, init=False)

    def generate_targets(
        self, event_date: date, history: pd.DataFrame
    ) -> list[TargetPosition] | None:
        """Rank trailing returns using history through event_date only."""
        if not self._seen_dates or self._seen_dates[-1] != event_date:
            self._seen_dates.append(event_date)
        if (len(self._seen_dates) - 1) % self.rebalance_every != 0:
            return None
        scores: list[tuple[str, float]] = []
        for ticker, group in history.groupby("ticker", sort=True):
            group = group.sort_values("date")
            if len(group) < self.lookback + 1:
                continue
            recent = group.iloc[-(self.lookback + 1) :]
            if float(recent.iloc[-1]["trading_value"]) < self.minimum_trading_value:
                continue
            score = float(recent.iloc[-1]["close"] / recent.iloc[0]["close"] - 1.0)
            scores.append((str(ticker), score))
        selected = sorted(scores, key=lambda item: (-item[1], item[0]))[: self.top_k]
        if not selected:
            return None
        if self.weighting == "score" and sum(max(score, 0.0) for _, score in selected) > 0:
            denominator = sum(max(score, 0.0) for _, score in selected)
            weights = [(ticker, max(score, 0.0) / denominator) for ticker, score in selected]
        elif self.weighting == "equal":
            weights = [(ticker, 1.0 / len(selected)) for ticker, _ in selected]
        else:
            raise ValueError("weighting must be 'equal' or 'score'")
        return [TargetPosition(ticker, weight) for ticker, weight in weights]

