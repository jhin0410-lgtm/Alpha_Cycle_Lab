# Prospective Causal Attribution v2.1

## Purpose

This contract extends the prospective decision ledger without turning realized returns into a post-hoc causal story.

The core separation is:

```text
Frozen thesis + prospective opportunity registration
                    |
                    v
        ProspectiveAttributionPlanSnapshot
             (before entry close)
                    |
                    v
        completed prospective ledger entry
                    |
                    v
      AttributionOutcomeEvidenceSnapshot
              (after horizon close)
                    |
                    v
   ProspectiveAttributionEvaluationSnapshot
```

Decision-time hypotheses, realized observations, and evaluation are different immutable snapshots. They are never stored as one mutable decision/outcome row.

## Frozen attribution layers

Decision System v2.1 already freezes four broad diagnostic layers:

1. `market`
2. `sector_theme`
3. `factor_regime`
4. `security_specific`

A prospective attribution plan must cover all four. This prevents the analyst from looking at the realized outcome first and then choosing only the layer that makes the story look persuasive.

The contract also allows narrower diagnostic domains:

- `macro_regime`
- `industry_transmission`
- `company_forecast`
- `market_expectation`
- `catalyst_timing`
- `valuation_repricing`
- `opportunity_selection`

The domains organize research errors. They do not independently establish causality.

## 1. Ex-ante attribution plan

`ProspectiveAttributionPlanSnapshot` binds:

- exact `ProspectiveOpportunityRegistration.snapshot_id`
- exact `InvestmentThesisSnapshot.snapshot_id`
- registered security
- evaluation date
- entry session
- 60 / 120 / 250 trading-day horizon
- active Decision System v2.1 guardrail evidence ID
- predeclared hypotheses across every frozen attribution layer

Each `AttributionHypothesis` records:

- hypothesis ID
- broad attribution layer
- diagnostic domain
- statement
- expected direction
- observable condition
- predecision evidence references
- explicit invalidation condition

The plan must be created after registration but no later than the registered entry-session close. The entry session is independently rederived from the registration timestamp and trading calendar.

A thesis created after the opportunity registration cannot be retroactively attached to the plan.

## 2. Post-outcome evidence

`AttributionOutcomeEvidenceSnapshot` is a separate post-outcome object.

It binds the exact attribution plan and exact `ProspectiveDecisionLedgerEntry`. The ledger target session is independently rederived from the registered entry session and the declared 60 / 120 / 250 trading-session horizon.

Outcome evidence cannot be captured before target-session close or before the ledger entry was scored.

Each observation must reference one preregistered hypothesis. Its layer and domain must exactly match the frozen hypothesis, so an observation cannot be reassigned to a more convenient explanation after the fact.

## 3. Mechanical evaluation

`ProspectiveAttributionEvaluationSnapshot` compares the frozen expected direction with post-outcome observations and emits only four statuses:

- `consistent`
- `inconsistent`
- `mixed`
- `insufficient`

The status logic is deliberately narrow:

- no usable observation → `insufficient`
- all usable observations match the preregistered direction → `consistent`
- one clear nonmatching direction → `inconsistent`
- conflicting observations, or an explicitly mixed observation → `mixed`

This is diagnostic consistency testing. An inconsistent macro hypothesis does **not** prove that macro caused the security return, and a consistent company forecast does **not** prove that the forecast caused the outperformance.

## Selection diagnostics

The evaluation carries the already-validated `ObservedDecisionAttribution` labels from the prospective decision ledger, such as whether the base Pareto frontier retained the best registered candidate or whether an expectation overlay improved frontier best return.

Those labels remain descriptive selection diagnostics. They are not converted into causal claims.

## Residual boundary

The active v2.1 guardrail explicitly prohibits promoting residual attribution to causal proof. The evaluation payload therefore freezes:

```text
diagnostic_attribution_only = true
residual_is_causal_proof = false
causal_conclusion_enabled = false
single_trade_architecture_update_enabled = false
portfolio_recommendation_enabled = false
automatic_execution_enabled = false
```

A single successful or failed prospective observation cannot alter architecture invariants.

## Persistence

Plan, outcome evidence, and evaluation are each content-addressed. Persistence uses exclusive file creation and refuses overwrite, including concurrent attempts to claim the same path.

This produces an auditable prospective chain instead of a mutable table that can silently rewrite what was believed before the outcome.

## Learning boundary

This module is the contract needed before later competence learning can be attempted across many independent or dependency-clustered observations.

A later learning layer may ask questions such as:

- Are macro-regime hypotheses repeatedly inconsistent in certain regimes?
- Does industry-transmission evidence provide useful information before company earnings revisions?
- Does expectation-gap research improve opportunity selection across independent observations?
- Which diagnostics remain useful after controlling for market, sector/theme, and factor-regime exposure?

Those questions require multiple prospective observations and explicit dependency handling. They must not be answered from a single trade.

## Frozen SK hynix boundary

This work does not modify, rescore, refit, or reparameterize the frozen SK hynix 2026Q3 company-gross-profit prospective experiment. Its outcome remains unavailable until the protected official filing is released.
