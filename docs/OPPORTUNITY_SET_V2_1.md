# Decision System v2.1 Cross-sectional Opportunity Set

The Opportunity Set is the first Decision System v2.1 layer that asks a portfolio-manager
question directly:

> At the same point in time and investment horizon, which fully researched securities offer a
> superior payoff/timing trade-off, and which trade-offs remain genuinely unresolved?

It is **not** a weighted stock score and it does not calculate an optimal portfolio.

## Research readiness is not attractiveness

Underwriter completeness and investment attractiveness are deliberately separated.

- `deep_ready`: eligible for the fully comparable capital-allocation surface.
- `deep_flagged`: also eligible, but epistemic warnings remain visible.
- `fast_ready`: remains a research candidate and is not silently promoted into the Deep Lane
  capital-allocation frontier, even when its provisional payoff looks attractive.
- `research_blocked`: excluded from the comparable frontier.

A security therefore cannot win merely because more research has been completed, and a Fast
Lane idea cannot outrank a Deep Lane candidate using evidence that has not passed the same gate.

## Fixed Pareto dimensions

Schema v1 uses exactly five transparent dimensions:

1. `bear_return_lower` — higher is better; less severe downside.
2. `base_return_lower` — higher is better.
3. `base_return_upper` — higher is better.
4. `bull_return_upper` — higher is better.
5. `nearest_catalyst_days` — lower is better.

The first four values come directly from the immutable Bear/Base/Bull payoff surface. Catalyst
timing comes from the earliest non-expired dated thesis catalyst.

A conditional catalyst without a certified earliest date does not receive an invented day
count. The candidate becomes partially incomparable until timing evidence improves.

## Pareto dominance

Candidate A Pareto-dominates candidate B only when A is no worse on all five fixed dimensions
and strictly better on at least one.

No weights are applied. A faster catalyst is not arbitrarily declared worth, for example, five
percentage points of downside. If one security offers better downside while another offers
better upside or faster timing, both remain on the non-dominated frontier.

A `unique_pareto_leader_security_id` is emitted only when at least two fully comparable Deep
Lane candidates exist and one candidate directly dominates every other comparable candidate.
Even then, it is **not** a BUY recommendation.

## Cost basis and sunk-cost protection

The candidate contract does not accept purchase price, historical cost basis, unrealized P&L,
or break-even price. Payloads explicitly state:

- `current_cost_basis_considered = false`
- `unrealized_pnl_considered = false`

This prevents a current capital-allocation decision from being distorted by the investor's
historical entry price.

## Epistemic flags

`deep_lane_ready_with_epistemic_flags` remains comparable because the underlying Deep Lane
package exists, but its flags remain attached to the candidate and the opportunity set records
that epistemically flagged research is present on the frontier.

The frontier therefore means *non-dominated on the declared dimensions*, not *high confidence*.

## Deliberately disabled

Schema v1 does not enable:

- weighted composite ranking score
- probability-weighted expected return
- scenario probabilities
- current-cost-basis ranking
- target price
- optimal portfolio weights
- Kelly sizing
- capital-allocation recommendation
- automatic execution

## Why Pareto first

The system does not yet possess sufficiently calibrated cross-sectional weights to claim that
one unit of catalyst speed, downside protection, or upside potential has a universally correct
exchange rate. Pareto dominance identifies decisions that are unambiguously better under the
frozen dimensions while preserving genuine trade-offs instead of hiding them inside arbitrary
weights.

## Next gate

The next high-value layer is an explicit **Decision View / Expectation-Gap contract** that can
select or combine a forecast from a preregistered tournament using a frozen rationale, then
compare that decision view with certified market consensus and conditional price-implied
requirements. That will add earnings-revision / surprise potential to the cross-sectional
surface without silently picking whichever forecast is most bullish.

After sufficient forward outcomes are accumulated, calibration can determine whether a richer
ranking model or portfolio-weighting rule earns the right to replace or augment Pareto-only
comparison.
