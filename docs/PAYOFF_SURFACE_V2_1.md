# Decision System v2.1 — Payoff Surface

## Purpose

The Underwriter needs more than an opaque `scenario_ref`. It needs a frozen downside/base/upside structure that can later be compared across opportunities without inventing calibrated probabilities that do not yet exist.

Schema v1 therefore requires exactly three conditional scenarios:

- bear;
- base;
- bull.

Each scenario contains a return range, not a point target.

## Required scenario content

Every scenario records:

- 60/120/250 trading-day horizon;
- trigger conditions;
- fundamental assumptions;
- catalyst references;
- evidence supporting the numeric payoff range;
- lower and upper price-return bounds;
- thesis-break conditions.

A numeric range without source evidence is rejected.

## False precision deliberately disabled

Schema v1 does not assign scenario probabilities. Consequently it does not calculate:

- probability-weighted expected return;
- expected value;
- Kelly sizing;
- mathematically optimal position size;
- target price.

The ranges remain conditional underwriting inputs until prospective history justifies stronger calibration.

## Point-in-time integrity

A `PayoffSurfaceSnapshot` binds one immutable `InvestmentThesisSnapshot`, the same thesis horizon, source snapshot ids, the active Decision System v2.1 guardrail evidence id, and the capture timestamp.

A payoff surface cannot be backdated before its thesis snapshot.

## Underwriter use

The future Deep Lane Underwriter should require this concrete payoff surface in addition to:

```text
full causal graph
forecast tournament
certified expectation
forward valuation
conditional price-implied requirement
counter-thesis / blind-spot package
opportunity-set comparison
portfolio-overlap assessment
```

The Underwriter may expose the observed payoff asymmetry and uncertainty, but it must not automatically approve a trade or manufacture probabilities from the three scenario labels.
