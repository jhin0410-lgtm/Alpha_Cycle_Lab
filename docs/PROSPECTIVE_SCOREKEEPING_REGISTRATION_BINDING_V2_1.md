# Prospective Scorekeeping Registration Binding v2.1

## Purpose

`ProspectiveOpportunityRegistration` is intentionally strict, but its low-level constructor can still be populated manually. Manual copying of snapshot IDs, candidate IDs, Pareto frontiers, or leaders creates an avoidable experiment-integrity risk.

This binding layer removes that risk for normal Decision System use.

## Typed registration path

`register_prospective_opportunity_set(...)` accepts the actual immutable:

- `OpportunitySetSnapshot`;
- optional `ExpectationAugmentedOpportunitySetSnapshot`.

It derives rather than accepts:

- base opportunity-set snapshot ID;
- candidate security universe;
- base Pareto frontier;
- base unique leader;
- expectation-overlay snapshot ID;
- expectation Pareto frontier;
- expectation unique leader;
- horizon;
- evaluation date;
- guardrail evidence ID;
- deterministic entry session.

The caller still supplies only information that is external to those research snapshots: registration identity/time, benchmark, adjusted price basis, source evidence, and trading calendar.

## Candidate-universe boundary

The prospective candidate universe is **not every researched security**.

It is exactly:

```text
OpportunitySetSnapshot.comparable_security_ids
```

This distinction matters. A fast-lane, blocked, or otherwise non-comparable research candidate should not later be counted as an opportunity-set selection error merely because its future stock return happened to be high. At the frozen decision time it was not eligible for the same capital-allocation comparison.

The binding requires at least two base-comparable securities because cross-sectional regret is not meaningful with a one-security opportunity set.

## Expectation-overlay binding

When an expectation overlay is included, the binding requires:

- overlay capture no later than registration;
- exact base opportunity-set snapshot ID match;
- identical evaluation date;
- identical investment horizon;
- identical Decision System guardrail evidence;
- overlay candidates equal every and only base-comparable security;
- overlay's preserved base frontier equal the base snapshot frontier;
- at least two expectation-comparable securities;
- a non-empty expectation Pareto frontier.

The last two requirements prevent an evidence-coverage failure from being mislabeled as a valid cross-sectional expectation-gap experiment.

Partial expectation coverage is still permitted when at least two candidates remain genuinely comparable. In later attribution this should be separated from pure frontier-selection skill.

## Time boundary

Neither the base opportunity set nor expectation overlay may be captured after `registered_at`.

The entry session is then derived with the scorekeeping core's frozen `next_available_session_close` rule. The caller cannot manually select an entry session through this API.

## Why this is a separate layer

The low-level scorekeeping dataclass remains useful as a serialization and validation contract. The typed binder is the normal construction path that proves the registration was derived from the actual Decision System snapshots rather than a hand-edited representation of them.

This separation keeps the scorekeeping schema stable while tightening experiment provenance.

## Explicitly not added

- no weighted score;
- no outcome-informed frontier changes;
- no benchmark optimization;
- no target price;
- no position sizing;
- no execution;
- no modification or execution of the frozen SK hynix 2026Q3 prospective experiment.

## Next gate

Once typed registration is stable, the next layer should aggregate immutable registrations and completed outcomes into a **prospective decision ledger**. That ledger should attribute errors to selection, expectation coverage, leader choice, path risk, and later thesis/catalyst/regime components without fitting a new score to a still-small sample.
