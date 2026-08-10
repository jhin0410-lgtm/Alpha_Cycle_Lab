# KIS forward estimate snapshot changes

This layer compares normalized KIS forward-estimate artifacts produced by `kis_forward_estimate_cli`.

It intentionally describes the result as a **change in the observed KIS estimate series**, not as a market-consensus revision. The source/aggregation methodology remains unverified.

## Run

```powershell
python -m alpha_cycle.kis_forward_estimate_revision_cli
```

Input:

```text
data/private/live-research/kis-forward-estimates
```

Output:

```text
data/private/live-research/kis-forward-estimate-changes
```

## One snapshot

With only one distinct source expectation snapshot, the tracker returns:

```text
status=estimate_change_baseline_only
estimate_snapshot_change_verified=false
```

This is the correct state. A single forward level cannot establish a revision.

Repeated normalization of the same source expectation snapshot does not create a second observation.

## Two or more snapshots

The tracker selects the two latest distinct source expectation snapshots and requires the same structural semantic binding. It compares common `(symbol, metric, period_label)` rows and records:

- previous and current KRW values;
- absolute change;
- percent change when the prior value is nonzero;
- `up`, `down`, or `unchanged` direction;
- added or dropped keys when the forward horizon changes.

No arbitrary materiality threshold is used. Direction only describes the sign of the observed change.

## Trust boundary

A successful two-snapshot comparison sets:

```text
estimate_snapshot_change_verified=true
provider_semantics_certified=false
consensus_certified=false
consensus_revision_certified=false
revision_certified=false
point_in_time_backtest_eligible=false
decision_score_enabled=false
```

This means the same historically crosschecked KIS row mapping changed between two immutable snapshots. It does not establish who produced the estimate, whether it is an analyst consensus, or whether the series is suitable for historical point-in-time backtesting.
