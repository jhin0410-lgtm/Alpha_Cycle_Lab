from datetime import date

import pandas as pd

from alpha_cycle.strategies.examples import CrossSectionalMomentumStrategy


def test_momentum_selects_top_assets_deterministically(prices: pd.DataFrame) -> None:
    strategy = CrossSectionalMomentumStrategy(
        lookback=3, top_k=1, rebalance_every=1, weighting="equal"
    )
    targets = None
    for event_date in sorted(pd.to_datetime(prices["date"]).dt.date.unique()):
        history = prices.loc[pd.to_datetime(prices["date"]).dt.date <= event_date].copy()
        history["date"] = pd.to_datetime(history["date"]).dt.date
        targets = strategy.generate_targets(date.fromisoformat(str(event_date)), history)
    assert targets is not None
    assert [(target.ticker, target.weight) for target in targets] == [("AAA", 1.0)]

