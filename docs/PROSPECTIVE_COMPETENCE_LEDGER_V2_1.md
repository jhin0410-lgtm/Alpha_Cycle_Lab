# Prospective Competence Ledger v2.1

## Purpose

The competence ledger is the learning layer after prospective decision scorekeeping and prospective causal-attribution diagnostics.

It answers a limited question:

> Across completed prospective observations, which preregistered research hypotheses repeatedly appear consistent, inconsistent, mixed, or insufficient under the same preregistered regime context, and how many distinct dependency clusters produced those observations?

It does **not** produce a scalar skill score, causal proof, portfolio weight, probability estimate, or automatic trade.

## Prospective chain

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
  [frozen no later than entry-session close]
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

The attribution plan must not predate the opportunity registration. The competence context must not predate the attribution plan and must be frozen no later than the registered entry-session close.

## Dependency clusters

A dependency cluster represents observations that may share the same underlying economic driver, evidence source, thesis mechanism, forecast dependency, or industry-cycle shock.

The ledger preserves two different counts:

- `raw_observation_count`
- `independent_dependency_cluster_count`

Three securities exposed to one memory-cycle inflection can therefore create three observations but only one dependency cluster. The cluster count is **not** claimed to be a statistically estimated effective sample size.

A single opportunity experiment may validly produce attribution evaluations for multiple registered securities. Those security-level observations may share one `ProspectiveDecisionLedgerEntry`; uniqueness is enforced on the competence context and attribution-evaluation identities rather than the experiment-wide ledger entry.

## Regime cohorts

Observations are grouped only by labels frozen before the outcome:

- 60 / 120 / 250 trading-day horizon
- `regime_taxonomy_id`
- `regime_bucket_id`

`regime_evidence_refs` are required in the ex-ante context registration. A later taxonomy change must use a new taxonomy identity rather than silently relabeling old observations.

## Downstream revalidation

The competence layer does not blindly trust a directly instantiated or deserialized attribution evaluation.

Before an attribution result can enter learning, it revalidates:

- active v2.1 guardrail evidence
- exact attribution-plan snapshot
- exact opportunity-registration snapshot identity carried by the context
- plan chronology relative to registration
- security, evaluation date, entry session, and horizon consistency
- exact attribution-evaluation and decision-ledger bindings
- every hypothesis ID, layer, and domain
- `expected_direction` against the frozen hypothesis
- `status` by recomputing it from `observed_directions`
- attribution layer summaries against the hypothesis-level results
- selection diagnostics against the validated decision-ledger entry
- observation chronology after both evaluation and ledger scoring

The mechanical status recomputation mirrors the attribution contract:

- no known observation → `insufficient`
- any explicit mixed observation → `mixed`
- all known observations equal the preregistered expected direction → `consistent`
- one known direction that excludes the expected direction → `inconsistent`
- otherwise → `mixed`

This prevents a serialized record from changing only its status or expected direction and contaminating the competence history.

## Aggregation

The ledger aggregates hypothesis results by:

- horizon
- preregistered regime taxonomy and bucket
- attribution layer
- attribution domain
- dependency cluster

It preserves counts of:

- `consistent`
- `inconsistent`
- `mixed`
- `insufficient`

It does not collapse these into a composite competence score.

## Architecture-learning quarantine

The payload explicitly keeps the following disabled:

```text
descriptive_learning_only = true
statistical_effective_sample_size_claimed = false
causal_skill_claim_enabled = false
composite_competence_score_enabled = false
probability_estimation_enabled = false
single_trade_architecture_update_enabled = false
architecture_change_proposal_bypassed = false
portfolio_optimization_enabled = false
automatic_execution_enabled = false
```

Repeated prospective evidence can later support a separately governed architecture-change proposal. It does not mutate architecture invariants directly.

## Immutable persistence

Context registrations, competence observations, and competence-ledger snapshots are content-addressed and written with exclusive-create semantics.

If writing, flushing, or `fsync` is interrupted even by `KeyboardInterrupt` or `SystemExit`, the partial file is removed before the interruption is re-raised. A truncated file therefore cannot permanently occupy an immutable evidence path and block a valid retry.

## Frozen SK hynix boundary

The frozen SK hynix 2026Q3 company-gross-profit prospective experiment remains unchanged. This ledger does not score it before the protected official outcome exists, does not refit the frozen model, and does not treat the unavailable outcome as a competence observation.
