# Expectation-Gap Opportunity Set v2.1

## Purpose

PR #289 established a cross-sectional Pareto surface over payoff ranges and catalyst timing. PR #290 added a preregistered internal Decision View and numeric gaps versus certified market consensus.

Those two layers must not be joined by simply appending every available expectation-gap number. A relative gap is cross-sectionally meaningful only when the comparison frame is frozen and semantically aligned.

This layer therefore keeps the original opportunity set intact and builds a separate, content-addressed overlay.

## Comparison frame

`ExpectationGapComparisonPolicySnapshot` is frozen before candidate gap snapshots and pins:

- evaluation date
- certified consensus provider ID
- expectation metric
- forward target date
- comparison statistic
- rationale and source evidence

Schema v1 permits only:

```text
consensus_relative_gap = (Decision View - certified provider consensus) / abs(provider consensus)
```

The provider, metric, or target date cannot be selected after inspecting gap values.

## Why the frame is strict

The following are not assumed interchangeable:

- revenue gap vs operating-income gap
- FY2026 gap vs 2026Q4 gap
- one provider's consensus construction vs another provider's construction
- a certified consensus gap vs a price-implied valuation requirement

A candidate that does not match the frozen frame receives an explicit blocker and no ranking value.

## Price-implied boundary

Price-implied requirements stay available as research evidence but do not enter cross-security ranking in this schema.

A 10x forward P/E reference for one industry is not automatically economically comparable with a 10x reference for another industry. A later version may admit price-implied dimensions only after an explicit cross-security valuation-frame certification contract exists.

## Base opportunity set remains authoritative

The overlay does not replace or mutate the base `OpportunitySetSnapshot`.

For every base-comparable security, the overlay requires exactly one expectation-gap candidate. Silent omission or substitution is rejected.

The augmented Pareto dimensions are:

- bear return lower bound: higher is better
- base return lower bound: higher is better
- base return upper bound: higher is better
- bull return upper bound: higher is better
- nearest dated catalyst days: lower is better
- certified consensus relative gap: higher is better

No exchange rate or weight is imposed between these dimensions.

## Interpretation

If a security dominated another candidate on payoff and catalyst timing but has a weaker certified expectation gap, the former unique leader can disappear. Both securities then remain non-dominated.

This is intentional. It distinguishes:

> a company with attractive standalone payoff

from:

> a company with attractive payoff that also differs positively from a comparable market expectation bar.

The system still does not calculate expected return probabilities or portfolio weights.

## Partial comparability

If fewer than two base-comparable securities also pass the expectation-gap frame, the overlay does not declare a unique expectation-augmented leader.

Flags include:

- `insufficient_expectation_comparable_candidates`
- `partial_expectation_gap_comparability`
- `multiple_expectation_augmented_non_dominated_opportunities`
- `expectation_gap_changes_pareto_frontier`

The base opportunity set remains visible regardless of overlay coverage.

## Explicitly disabled

- provider aggregation
- post-hoc provider selection
- post-hoc metric selection
- post-hoc target-period selection
- price-implied cross-security ranking
- weighted composite scores
- cost-basis ranking
- target prices
- capital-allocation recommendations
- automatic execution

## Frozen SK hynix boundary

This layer does not modify the frozen SK hynix 2026Q3 prospective experiment, feature vector, estimator, forecast, benchmark, source capture, or outcome scorer.

## Next gate

Once this overlay is stable, the highest-value next step is prospective decision scorekeeping rather than adding more heuristic dimensions.

A decision ledger should freeze each opportunity-set observation and later attach realized 60/120/250-trading-day outcomes, benchmark/sector excess returns, max adverse excursion, max favorable excursion, thesis/catalyst realization, and opportunity-cost regret. That evidence can eventually calibrate which decision dimensions deserve more or less weight without inventing weights today.
