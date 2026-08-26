# Prospective Forecast Tournament and 3/6/12M Opportunity Set v2.1

## Authority audit

The repository contains several distinct forecast classes which must not be collapsed:

| Existing artifact | Classification | Tournament role |
|---|---|---|
| SK hynix 2026Q3 locked company-GP affine OLS | genuinely prospective internal deterministic model | external frozen reference; generic eligibility blocked because the legacy artifact has no exact training-cutoff timestamp |
| SK hynix 2026Q3 lagged-GP persistence | preregistered benchmark | one eligible benchmark; insufficient alone for a winner |
| historical company-GP evaluations and PIT panel | historical/backtest | lineage and report-only performance, never a prospective candidate |
| KIS forward cells | provider estimate, non-certified numeric authority | excluded |
| scenario/expectation/valuation paths | internal model or unsupported assumptions | excluded while their authority gates remain closed |
| PM/human forecast | none currently preregistered | unavailable |

The frozen experiment remains outcome blind. Its `q3_source_outcome_loaded` and `q3_evaluated`
flags are false, so this milestone does not score it or infer an outcome.

## Registration and replay

The adapter reads the frozen source once, rejects aliases, checks stable file identity across the
read, rejects malformed UTF-8, duplicate JSON keys, unknown fields, bool/number aliases and source
identity drift, then runs the existing scientific artifact validator against those exact bytes.
Every candidate binds source bytes, model/protocol identities, inputs, cutoffs, target semantics,
unit, accounting basis, outcome definition, scoring rule, tournament and frozen selection rule.

A normalized caller-created bundle cannot publish itself: persistence first reconstructs it from
the frozen upstream bytes. Publication is an immutable, content-addressed directory rename with no
mutable `latest` pointer. Replay is offline and again reconstructs the complete bundle.

## Real acceptance

The acceptance universe is `000660` and `005930` at 3M (63 sessions), 6M (126), and 12M (252).
All six records expose the same explicit missing-data policy:

`never_numeric_neutral_never_weight_renormalize`

- SK hynix 3M can reference the frozen Q3 experiment, but is `INCOMPARABLE`: only its benchmark
  satisfies the newer generic registration fields; the internal model lacks an exact training
  cutoff timestamp in the immutable legacy artifact.
- SK hynix 6M/12M and all Samsung horizons have no comparable prospective forecast.
- Market state is measured but non-directional and cannot become forecast authority.
- Estimate revision history remains non-authoritative.
- Dated source-backed catalysts are unavailable.
- Valuation, price-implied expectation and scenario/payoff remain blocked by #309 conclusions.
- Actual earnings trajectory comparison remains unavailable until exact compatible period and
  statement-basis evidence is supplied.

Therefore partial rank and overall rank are unavailable for every horizon. No missing field is
converted to zero or neutral, no weights are renormalized, and no winner is declared.

## Frozen protection

This module only reads the two existing private 2026Q3 trees. It never writes to their paths and
does not load a 2026Q3 outcome. Their before/after file and tree SHA-256 values are verified as a
merge gate.
