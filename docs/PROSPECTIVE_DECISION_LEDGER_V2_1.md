# Prospective Decision Ledger v2.1

## Purpose

The prospective decision ledger is the first Decision System v2.1 learning surface that aggregates completed prospective opportunity experiments without converting the observations into a new ranking score.

It answers a narrow question:

> Given the opportunity set, Pareto frontiers, leaders, benchmark, horizon, and price basis that were frozen before the outcome, what did the registered decision surface retain or miss after the horizon actually closed?

It does **not** answer whether a thesis was causally correct, whether a macro regime call was correct, or whether a new portfolio weight should be used.

## Upstream chain

```text
OpportunitySetSnapshot
        |
        +-- optional ExpectationAugmentedOpportunitySetSnapshot
        |
ProspectiveOpportunityRegistration
        |
ProspectiveOpportunityOutcomeSnapshot
        |
ProspectiveDecisionLedgerEntry
        |
ProspectiveDecisionLedgerSnapshot
```

A ledger entry revalidates the content-addressed links between the opportunity set, registration, realized outcome, and optional expectation overlay before accepting the observation.

## Entry-level diagnostics

The ledger records only directly observable ex-post selection diagnostics:

- ex-post winner security IDs inside the preregistered candidate universe
- best registered candidate return
- base Pareto frontier best return
- base Pareto frontier regret
- whether the base frontier contained an ex-post winner
- unique base leader regret, when a unique leader existed
- expectation Pareto frontier best return and regret, when an overlay was registered
- expectation-overlay incremental best return relative to the base frontier
- expectation coverage status
- unique expectation leader regret, when a unique expectation leader existed

The corresponding attribution labels are descriptive, for example:

- `base_frontier_retained_best_registered_candidate`
- `base_frontier_missed_best_registered_candidate`
- `unique_base_leader_matched_best_registered_return`
- `unique_base_leader_underperformed_best_registered_return`
- `expectation_overlay_improved_frontier_best_return`
- `expectation_overlay_degraded_frontier_best_return`
- `expectation_overlay_left_frontier_best_return_unchanged`
- `expectation_coverage_complete`
- `expectation_coverage_partial`

These labels are not causal explanations.

## Cohorts

Observations are aggregated only inside the same:

- investment horizon: 60 / 120 / 250 trading days
- adjusted price basis

A cohort summary reports descriptive statistics such as:

- observation count
- base-frontier winner-containment rate
- mean and median base-frontier regret
- unique-base-leader match rate
- expectation-overlay observation count
- expectation complete/partial coverage counts
- expectation-frontier winner-containment rate
- mean and median expectation-frontier regret
- overlay improved / degraded / unchanged counts
- mean and median expectation-overlay incremental best return

The ledger does not pool different horizons into one score.

## Provenance and anti-hindsight boundary

The ledger rejects observations when the registered and realized objects do not reconcile. Examples include:

- registration points to another opportunity-set snapshot
- candidate universe differs from the base capital-allocation-comparable universe
- registered Pareto frontier or leader differs from the frozen opportunity set
- outcome points to another registration snapshot
- outcome candidate universe differs from the registration
- benchmark, horizon, price basis, or entry session drift
- benchmark-excess return arithmetic drift
- ex-post winner, frontier regret, leader regret, or overlay incremental-return drift
- a registered expectation overlay is missing or replaced by another snapshot

The outcome is therefore not trusted merely because it is a valid dataclass. Decision metrics are recomputed from the frozen candidate returns before a ledger entry is accepted.

## Explicitly disabled

The ledger payload freezes the following boundaries:

```text
descriptive_statistics_only = true
causal_skill_inference_enabled = false
weighted_score_training_enabled = false
probability_estimation_enabled = false
portfolio_optimization_enabled = false
automatic_execution_enabled = false
```

Prospective observations must accumulate before any later calibration or model-selection work is considered. The ledger must not be used to retrofit a weighted ranking formula to a small number of realized outcomes.

## Persistence

`ProspectiveDecisionLedgerSnapshot` is content-addressed. Persistence includes its snapshot SHA-256 and refuses overwrite of an existing path.

This creates immutable checkpoints of the learning history rather than a mutable score table whose past can be silently rewritten.

## What comes next

The ledger establishes **selection-performance evidence**. A later attribution layer may bind thesis claims, causal graph edges, catalysts, regime evidence, forecast-tournament results, and valuation evidence to distinguish errors such as:

- macro/regime miss
- industry transmission miss
- company forecast miss
- market-expectation miss
- catalyst timing miss
- valuation/repricing miss
- opportunity-selection miss

Those classifications require their own prospective evidence contracts. They are intentionally not inferred by this ledger.

## Frozen research boundary

The existing SK hynix 2026Q3 frozen prospective company-gross-profit experiment is not modified, rescored, or reparameterized by this ledger work.
