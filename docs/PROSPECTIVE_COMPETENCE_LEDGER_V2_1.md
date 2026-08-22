# Prospective Competence Ledger v2.1

## Purpose

The competence ledger is the next learning layer after prospective decision scorekeeping and prospective causal-attribution diagnostics.

It answers a deliberately limited question:

> Across completed prospective observations, which preregistered research hypotheses repeatedly appear consistent, inconsistent, mixed, or insufficient under the same preregistered regime context, and how many genuinely distinct dependency clusters produced those observations?

It does **not** answer whether the investor has a single scalar “skill score,” whether a pattern is causal, or how much capital should be allocated.

## Why another preregistration is required

If regime labels or dependency clusters are assigned only after outcomes are known, the learning system can manufacture flattering groups after the fact.

Therefore the chain is:

```text
ProspectiveAttributionPlanSnapshot
        +
ProspectiveOpportunityRegistration
        |
        v
CompetenceContextRegistration
  - dependency_cluster_id
  - regime_taxonomy_id
  - regime_bucket_id
  - regime evidence
  [frozen before entry close]
        |
        v
ProspectiveAttributionEvaluationSnapshot
        +
ProspectiveDecisionLedgerEntry
        |
        v
CompetenceObservationSnapshot
        |
        v
ProspectiveCompetenceLedgerSnapshot
```

The context registration must exist after the attribution plan and no later than the registered entry-session close.

## Dependency clusters

A dependency cluster represents observations that may share the same underlying economic driver, evidence source, thesis mechanism, or forecast dependency.

Examples could include multiple securities whose prospective theses are all driven by the same memory-cycle inflection or the same defense-budget shock.

The ledger keeps two different counts:

- `raw_observation_count`
- `independent_dependency_cluster_count`

If three observations belong to one shared dependency cluster, the system records three raw observations but only one dependency cluster. It does not call the cluster count a statistically estimated effective sample size.

The payload freezes:

```text
statistical_effective_sample_size_claimed = false
```

## Regime cohorts

Observations are grouped only by labels frozen before the outcome:

- 60 / 120 / 250 trading-day horizon
- `regime_taxonomy_id`
- `regime_bucket_id`

The taxonomy ID distinguishes different regime-classification systems. This prevents a future change in regime definitions from silently rewriting old observations into a new taxonomy.

## What is aggregated

Each competence observation copies the mechanically evaluated attribution-hypothesis statuses from the frozen attribution plan:

- `consistent`
- `inconsistent`
- `mixed`
- `insufficient`

The ledger aggregates counts by attribution layer and diagnostic domain. It also preserves the descriptive selection diagnostics already validated by the prospective decision ledger.

No single composite score is produced.

## Why no competence score yet

A ratio such as “70% correct” would be misleading when observations share drivers, regimes, evidence sources, and security exposures. It would also collapse different kinds of research errors into one number.

The ledger therefore reports recurrence structure instead of an optimized score:

- raw observation count
- dependency-cluster count and per-cluster observation counts
- status counts for each layer/domain pair
- regime and horizon cohort identity

A later method may compare patterns across sufficiently accumulated independent clusters, but that method requires its own frozen policy and validation.

## Architecture-learning quarantine

Decision System v2.1 explicitly prohibits one trade outcome from changing architecture invariants.

The competence ledger therefore freezes:

```text
descriptive_learning_only = true
causal_skill_claim_enabled = false
composite_competence_score_enabled = false
probability_estimation_enabled = false
single_trade_architecture_update_enabled = false
architecture_change_proposal_bypassed = false
portfolio_optimization_enabled = false
automatic_execution_enabled = false
```

Repeated observations may later support an explicit architecture-change proposal. They do not mutate the architecture directly.

## Anti-hindsight checks

The implementation revalidates:

- exact attribution-plan snapshot
- exact opportunity-registration snapshot
- active v2.1 guardrail evidence
- entry rule and derived entry session
- context registration no later than entry close
- exact attribution-evaluation snapshot
- exact prospective-decision-ledger entry
- security and horizon consistency
- all frozen attribution hypotheses retained
- evaluation layer/domain matches the preregistered hypothesis
- selection diagnostics match the validated ledger entry
- competence observation created after evaluation and ledger scoring

## Immutable persistence

Context registrations, completed competence observations, and competence-ledger snapshots are all content-addressed and persisted with exclusive-create semantics. Existing evidence cannot be silently overwritten.

## Frozen SK hynix boundary

The frozen SK hynix 2026Q3 company-gross-profit forecast remains unchanged. The competence ledger does not score it before the protected official outcome exists, does not refit the model, and does not treat the currently unavailable outcome as a learning observation.
