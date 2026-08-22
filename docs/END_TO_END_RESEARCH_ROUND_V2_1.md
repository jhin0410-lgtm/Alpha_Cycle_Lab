# End-to-End Research Round Orchestrator v2.1

## Purpose

Decision System v2.1 already contains separate typed contracts for thesis state, Underwriter readiness, payoff surfaces, Decision Views, expectation gaps, cross-sectional opportunity comparison, prospective scorekeeping, and later learning.

The orchestrator is the integration spine across those contracts. It does not create a parallel investment model.

Its job is to answer:

> At one declared point in time and one 60 / 120 / 250 trading-day horizon, can the existing typed research evidence be assembled into a semantically consistent cross-sectional decision surface, and if not, exactly what prevents it?

Missing evidence is returned as a structured blocker. It is never replaced with a neutral score, a guessed value, a web lookup, or a synthetic snapshot.

## Inputs

Each `ResearchSecurityPackage` starts with one immutable `InvestmentThesisSnapshot` and may carry:

- `UnderwritingReadinessSnapshot`
- `PayoffSurfaceSnapshot`
- `DecisionViewSnapshot`
- `DecisionExpectationGapSnapshot`

The package intentionally allows the latter contracts to be absent. This lets a real research round diagnose incomplete evidence rather than requiring callers to fabricate objects before invoking the orchestrator.

## Point-in-time boundary

Every supplied source snapshot must have been captured no later than the round cutoff. The orchestrator also rechecks:

- thesis horizon against round horizon;
- Underwriter thesis/security/evaluation-date/guardrail binding;
- payoff thesis/security/horizon/guardrail binding;
- Decision View security/evaluation-date/guardrail binding;
- expectation-gap Decision View/security/target/evaluation-date/guardrail binding.

A mismatch creates a `ResearchRoundBlocker` instead of being silently repaired.

## Existing logic is reused

When a security package is internally consistent, the orchestrator calls the existing:

- `build_opportunity_candidate()`
- `build_opportunity_set()`
- optional expectation-gap opportunity candidate builder
- optional expectation-augmented opportunity-set builder
- optional typed prospective scorekeeping registration binder

The orchestrator therefore does not reimplement Pareto dominance, catalyst timing, Deep-Lane eligibility, expectation-gap comparability, or scorekeeping registration semantics.

`research_logic_reimplemented = false` is frozen into every round payload.

## Round statuses

### Prospective

- `prospective_blocked`: at least one research/provenance/comparability blocker exists.
- `prospective_ready_for_registration`: the research surface is cross-sectionally comparable but no scorekeeping registration was requested.
- `prospective_registered`: the research surface passed and the existing typed scorekeeping binder created an immutable prospective registration.

`prospective_registered` is **not** an investment recommendation and is not a completed future outcome.

### Replay

- `replay_blocked`: the historical PIT package is incomplete or inconsistent.
- `replay_ready`: the research package can be reconstructed at the declared cutoff.

Replay mode cannot create a new prospective scorekeeping registration.

## Structured blockers

A blocker records:

- component
- stable code
- detail
- optional security ID
- optional source snapshot ID

Examples include:

- `underwriting_snapshot_missing`
- `payoff_surface_missing`
- `thesis_after_round_cutoff`
- `underwriting_thesis_mismatch`
- `expectation_gap_target_mismatch`
- `opportunity_candidate_coverage_incomplete`
- `insufficient_capital_allocation_comparable_candidates`
- `expectation_gap_missing_for_comparable_security`
- `prospective_registration_failed`

This is the mechanism intended for the first real repo-evidence-only research round: a blocked result becomes a prioritized evidence-acquisition list instead of a false investment conclusion.

## Expectation overlay

The expectation-gap overlay remains optional because a base payoff/catalyst opportunity set is a valid typed research surface on its own.

When an `ExpectationGapComparisonPolicySnapshot` is supplied, however, the overlay fails closed. Every base-comparable security must have a policy-aligned expectation-gap snapshot. Silent omission is prohibited.

Price-implied requirements remain upstream research evidence and are not promoted to cross-security market-consensus ranking by this orchestrator.

## Prospective registration

A `ProspectiveRegistrationRequest` contains only inputs external to the research snapshots:

- registration ID and timestamp
- benchmark security
- adjusted price basis
- source evidence
- trading calendar

The candidate universe, Pareto frontier, leader, horizon, evaluation date, guardrail evidence, and deterministic entry session remain derived by the existing typed scorekeeping binder.

Raw price basis is rejected.

## Explicitly disabled

Every `ResearchRoundSnapshot` records:

```text
point_in_time_fail_closed = true
missing_evidence_neutralized = false
research_logic_reimplemented = false
automatic_investable_now_transition_enabled = false
target_price_enabled = false
optimal_position_size_enabled = false
portfolio_recommendation_enabled = false
automatic_execution_enabled = false
future_outcome_claimed = false
```

A ready or registered round means only that the frozen research contracts are sufficiently connected for their declared purpose.

## Decision / outcome separation

The orchestrator does not attach realized future performance. Existing prospective scorekeeping, decision-ledger, causal-attribution, and competence-ledger layers remain downstream and temporally separate.

This preserves:

```text
DecisionSnapshot != OutcomeSnapshot
```

and prevents a research-round assembler from becoming a hindsight scoring surface.

## Immutable persistence

`ResearchRoundSnapshot` is content addressed. Persistence uses exclusive-create semantics and removes a partial file if writing is interrupted. Existing round evidence cannot be silently overwritten.

## Frozen SK hynix 2026Q3 boundary

This module does not refit, modify, rescore, repair, or execute the frozen SK hynix 2026Q3 company-gross-profit prospective experiment. The protected forecast and its future official-outcome scorer remain separate.

## First practical use

The first practical prospective plumbing round should be `000660` versus `005930` using repository evidence only.

The procedure is deliberately strict:

1. search the repository for real typed thesis, Underwriter, payoff, Decision View, and expectation-gap artifacts;
2. supply only those that actually exist and are PIT-compatible;
3. do not fetch the web merely to make the round pass;
4. run the orchestrator;
5. treat `prospective_blocked` blocker codes as the actual evidence-acquisition backlog;
6. register prospective scorekeeping only after at least two securities are genuinely capital-allocation comparable.

A blocked first run is scientifically useful. It identifies where Alpha Cycle Lab still lacks operational evidence rather than pretending the architecture is already a live investment engine.
