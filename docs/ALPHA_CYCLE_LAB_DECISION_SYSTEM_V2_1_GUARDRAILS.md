# Alpha Cycle Lab — Decision System v2.1 Epistemic Guardrail Addendum

## 1. Status and purpose

Decision System v2.1 is a **successor guardrail policy**. It does not rewrite or replace
`decision_system_v2_policy.v1.yaml`.

The v2 architecture remains the historical architecture freeze. v2.1 adds defenses that became
necessary before deeper integration:

- independent counter-thesis construction;
- outside-graph blind-spot discovery;
- decision-complexity budgeting;
- generic prospective forecast governance;
- fast/deep research lanes;
- decision/outcome immutability;
- factor-aware diagnostic attribution;
- architecture-learning quarantine.

The purpose is to reduce the chance that Alpha Cycle Lab becomes a precise confirmation-bias engine
or overfits its architecture to a small number of successful or failed trades.

## 2. Predecessor immutability

The successor policy binds to the exact content-addressed v2 policy.

Rules:

1. v2 is not edited to pretend v2.1 was always present.
2. v2.1 carries the predecessor policy evidence id.
3. loading v2.1 fails if the predecessor no longer reproduces the pinned evidence id.
4. historical policies cannot be rewritten.
5. the frozen SK hynix 2026Q3 prospective research round remains unchanged.

Correctness repairs to code that failed to enforce the already-frozen v2 contract are permitted.
They are not architecture rewrites.

## 3. Independent counter-thesis

Opposing evidence inside a human-authored thesis graph is necessary but insufficient.

Before `investable_now`, the successor architecture requires an independent counter-thesis process
whose construction is not simply a support-search continuation.

The future `CounterThesisSnapshot` must preserve at least:

- strongest alternative explanation;
- falsification evidence;
- missing evidence;
- unresolved contradictions;
- status and lineage.

The counter-thesis is not required to be correct. It is required to be independently represented.

## 4. Outside-graph discovery

Red-team analysis asks whether the existing graph is wrong.

Outside-graph discovery asks whether the graph is incomplete.

Before `investable_now`, the system must explicitly search for candidate material variables that the
current thesis does not contain. Candidate blind spots remain evidence until promoted through a later
thesis snapshot.

Typical examples include:

- FX or funding conditions;
- customer concentration;
- competitor yield/capacity;
- regulation/export controls;
- flow/positioning;
- capital-return policy;
- multiple-regime changes.

## 5. Complexity budget

The cap applies to **critical state variables**, not to evidence.

The v2.1 maximum is five critical state variables per decision thesis.

This prevents a thesis from becoming unfalsifiable through endless driver accumulation while allowing
each critical variable to carry many evidence nodes.

Principle:

> Decision complexity is capped; evidence complexity is not.

## 6. Forecast governance

Decision-relevant forecasts must be prospective research objects.

The generic forecast ledger to follow this guardrail must separate:

1. immutable forecast registration;
2. later outcome observation;
3. later evaluation.

A registration must have a dependency-cluster identity so repeated forecasts driven by the same
economic shock are not mistaken for independent evidence.

Forecast performance is recorded as a vector:

- accuracy;
- calibration;
- decision relevance;
- information gain;
- difficulty.

v2.1 prohibits converting those dimensions into one composite score before enough prospective history
exists to justify the weighting.

## 7. Fast and deep research lanes

### 7.1 Fast lane

Fast lane exists for time-sensitive events where a full underwriting package cannot yet be completed.

It may support `research_priority` or `underwriting`. It does not permit automatic execution.

Minimum elements:

- why now;
- catalyst;
- transmission path;
- expectation or priced-in assessment;
- top downside;
- counter-thesis;
- kill condition;
- position uncertainty.

The policy may represent a small exploratory exposure as a **human-review-only concept**. No account or
order capability is introduced.

### 7.2 Deep lane

`investable_now` requires deep-lane research.

Minimum elements:

- full causal graph;
- forecast tournament;
- certified expectation;
- valuation;
- payoff surface;
- counter-thesis;
- outside-graph scan;
- opportunity-set comparison;
- portfolio overlap.

This converts research depth into an allowed conviction tier rather than a binary rule that all
incomplete analysis must be ignored.

## 8. Decision and outcome separation

A decision snapshot and an outcome snapshot must be distinct immutable objects.

A mutable row that begins as a decision and is later overwritten with realized results is prohibited.

This preserves:

- what was believed;
- what action was considered;
- what was later observed;
- what was learned.

The rule also prevents hindsight from leaking into the original thesis representation.

## 9. Diagnostic attribution

Return attribution must separate at least:

- market;
- sector/theme;
- factor/regime;
- security-specific residual.

This is diagnostic decomposition, not causal proof.

A residual return cannot automatically be labeled stock-picking alpha.

Formal attribution should remain limited until enough prospective decision history exists.

## 10. Architecture-learning quarantine

Alpha Cycle Lab must not add a rule every time one trade succeeds or fails.

A future `ArchitectureChangeProposal` is required before architecture invariants change.

A single trade outcome cannot change an invariant.

Narrow correctness exceptions are:

- look-ahead bug;
- provenance violation;
- accounting error;
- security or safety defect.

These exceptions correct invalid system behavior rather than optimize the architecture to a realized
trade.

## 11. v2 contract enforcement repairs included with this addendum

Review of the already-merged v2 implementation identified enforcement gaps. These repairs do not alter
the frozen v2 policy; they make the implementation enforce what v2 already claimed.

The loader must now:

- reject quoted or malformed booleans instead of using Python truthiness;
- validate every frozen research-governance boolean;
- validate portfolio-overlap and opportunity-cost requirements;
- validate migration invariants;
- preserve the historical scorecard as diagnostic infrastructure;
- preserve the SK hynix 2026Q3 boundary.

An `investable_now` thesis must now have:

- a kill condition;
- portfolio-overlap assessment;
- opportunity-set comparison;
- at least one catalyst clock;
- at least one payoff scenario;
- an evidence-backed market-expectation claim.

These are enforcement repairs, not new post-hoc investment rules.

## 12. Sequencing after this guardrail

The correct development sequence is:

```text
v2 architecture freeze
        ↓
certified expectation state
        ↓
v2.1 epistemic guardrail successor
        ↓
generic forecast ledger
        ↓
counter-thesis / blind-spot objects
        ↓
revalidate parked forward-valuation implementation
        ↓
price-implied expectation
        ↓
semiconductor causal engine
        ↓
fast/deep underwriter
        ↓
opportunity ranking / allocation
        ↓
prospective history
        ↓
forecast / decision / return attribution
        ↓
competence maps and calibrated allocation only if justified
```

The already-built forward-valuation code is not discarded. Its merge is delayed until it has been
revalidated against the successor guardrails.

## 13. Non-goals of this addendum

This addendum does not:

- build the generic forecast ledger yet;
- build automatic counter-thesis generation yet;
- build blind-spot search yet;
- compute target prices;
- enable fair-value scoring;
- enable automatic orders;
- change the v1 composite score;
- change the SK hynix 2026Q3 forecast, source lock, benchmark, or outcome scorer.

The next implementation PR after this guardrail should build the generic prospective forecast ledger.
