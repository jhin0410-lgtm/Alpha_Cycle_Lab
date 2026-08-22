# Decision View / Expectation Gap v2.1

## Purpose

Decision System v2.1 needs one explicit internal forward view before it can ask whether Alpha Cycle Lab knows something different from the market.

This layer does **not** select the most bullish forecast, average a tournament after seeing outcomes, claim a fair value, or emit a trade. It freezes how one preregistered forecast identity becomes the human-PM Decision View and then compares that view with external bars that are already certified by upstream contracts.

## Architecture

```text
preregistered selection rule
        ↓
comparable forecast tournament
        ↓
internal Decision View
        ├──────────────→ certified market consensus provider A → consensus gap A
        ├──────────────→ certified market consensus provider B → consensus gap B
        └──────────────→ conditional price-implied reference surfaces → price-implied gaps
```

The outputs remain research evidence for human PM review.

## 1. Preregistered selection rule

`DecisionViewSelectionRuleSnapshot` is content addressed and registered before candidate forecast values.

It pins:

- security
- target variable
- target date
- unit
- forecaster kind
- model family
- rationale
- source evidence
- active Decision System v2.1 guardrail evidence

The current schema supports `pinned_forecaster_identity` only.

Explicitly disabled:

- choosing the most bullish forecast after values are known
- automatic ensemble weighting
- hidden model substitution

## 2. Decision View

`build_decision_view()` first requires the existing Underwriter forecast-tournament comparability contract to pass.

All candidate forecasts must share the relevant target and forecast-tournament semantics. The preregistered identity must resolve to exactly one forecast.

The resulting immutable Decision View records:

- selected forecast snapshot and forecast ID
- selected forecaster kind and model family
- selected numeric value
- forecast origin
- information cutoff
- all tournament forecast snapshot IDs
- whether forecast dependency overlap exists

A Decision View is an internal research view. It is not market consensus, a target price, or a trade instruction.

## 3. Certified consensus gaps

A numeric consensus gap is computed only when an `ExpectationStateSnapshot` contains an observation matching all of:

- security
- metric
- target-period end date
- unit
- `market_consensus` expectation kind
- independent market-consensus certification

For each provider, the layer stores:

```text
absolute_gap = decision_view - provider_consensus
relative_gap = absolute_gap / abs(provider_consensus)
```

when the denominator is non-zero.

Providers are not averaged. Disagreement across independently certified providers remains visible rather than being hidden in one synthetic consensus number.

Single-broker, management-guidance, or provider-defined rows are not silently relabelled as consensus.

## 4. Price-implied gaps

When a compatible `PriceImpliedRequirementSnapshot` is supplied, the Decision View is separately compared with each available conditional reference point for the same operating metric and target period.

The Decision View is converted to KRW only for explicitly supported units:

- KRW
- KRW thousand
- KRW million
- KRW billion
- KRW trillion

Each conditional reference remains separate. No reference multiple is selected as the unique market expectation.

A price-implied gap therefore means:

> under this frozen valuation reference frame, how far is the internal operating view above or below the operating value required by the current market capitalization?

It does **not** mean that the market literally holds that operating forecast.

## 5. Epistemic flags

Forecast dependency overlap is preserved into the expectation-gap snapshot.

If no price-implied surface is supplied, or no comparable metric/period exists, the condition is surfaced as a flag instead of being numerically invented.

## 6. Disabled outputs

This layer explicitly keeps the following disabled:

- consensus-provider aggregation
- price-reference aggregation
- probability-weighted expected return
- decision composite score
- target price
- optimal position sizing
- automatic execution

## 7. Relationship to the cross-sectional opportunity set

The Pareto opportunity-set layer merged in PR #289 compares payoff and catalyst dimensions. This Decision View layer adds the missing research primitive required for a later opportunity-set extension:

- internal-vs-consensus expectation gap
- internal-vs-price-implied operating burden
- forecast dependency warning

That later extension must still avoid a universal weighted magic score. Expectation-gap dimensions should be added only after direction, scaling, freshness, and cross-sector comparability are explicitly frozen.

## 8. Frozen SK hynix prospective experiment boundary

This work does not modify the frozen SK hynix 2026Q3 prospective gross-profit experiment, its feature vector, estimator, forecast, benchmark, source capture, or preregistered outcome scorer.

Existing frozen forecasts may be referenced by the generic ledger only under their already-established provenance semantics.

## 9. Next gate

After this contract is merged, the next high-value gate is to integrate Decision View evidence into the cross-sectional opportunity candidate without collapsing it into an arbitrary scalar score.

The preferred design is a typed expectation-gap dimension set with fail-closed comparability rules, followed by prospective scorekeeping across 60/120/250 trading-day horizons.
