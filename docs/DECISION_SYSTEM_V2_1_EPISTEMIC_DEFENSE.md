# Decision System v2.1 — Epistemic Defense Contracts

## Purpose

This layer operationalizes the epistemic-defense requirements frozen in Decision System v2.1 without turning them into an automatic trading signal.

The original thesis remains immutable. Independent challenge evidence is recorded in separate content-addressed objects.

## Objects

### `CounterThesisSnapshot`

A counter-thesis is not merely an `opposing_evidence` field appended to the original human thesis. It must be constructed through an independent challenge pass.

Required properties include:

- exact frozen `thesis_snapshot_id`;
- `created_without_thesis_support_search = true`;
- explicit independence method and search scope;
- at least one alternative explanation;
- one identified strongest alternative explanation;
- falsifiers and missing evidence;
- unresolved contradictions preserved rather than silently reconciled;
- append-only parent lineage for later revisions.

Observed facts, accounting identities, and empirically validated counter-explanations require evidence references. Economic hypotheses may exist without certified evidence only when they remain explicitly labelled as hypotheses.

### `BlindSpotDiscoverySnapshot`

Outside-graph discovery asks a different question from red-team testing:

> What material variable may be missing from the current decision representation entirely?

The scan therefore records the current critical-state variables and requires that those graph variables be used as an exclusion set.

Decision complexity remains capped at five critical state variables. Evidence complexity is not capped.

Each candidate records:

- candidate variable;
- mechanism;
- materiality;
- evidence references;
- whether it is already covered;
- recommendation to promote, monitor, reject as immaterial, or leave unresolved;
- rationale.

High-materiality candidates require evidence. Promotion to a critical variable requires evidence and cannot be used for a variable already represented in the graph.

An empty scan is allowed only if the completed search records why no uncovered candidate survived the screen. Search limitations are mandatory because absence of a discovered blind spot is not proof that none exists.

### `EpistemicDefensePackageSnapshot`

The package binds one thesis snapshot to one counter-thesis snapshot and one blind-spot snapshot under the same v2.1 guardrail evidence id.

It surfaces diagnostics such as:

- high-materiality alternative explanations;
- high-materiality unresolved contradictions;
- uncovered high-materiality blind spots;
- candidates proposed for promotion to a critical variable;
- missing counter-thesis evidence.

It does **not** approve an investment.

The package explicitly keeps:

- decision score disabled;
- investability decision disabled;
- automatic execution disabled.

A later Underwriter may consume this package, but must make its own explicit gating decision.

## Historical integrity

The epistemic-defense objects never mutate:

- the predecessor Decision System v2 policy;
- the v2.1 guardrail policy;
- an existing thesis snapshot;
- any frozen SK hynix 2026Q3 feature, forecast, benchmark, source lock, or future outcome scorer.

Later counter-thesis or blind-spot work must create a new snapshot with a content-addressed parent reference.

## Why this matters

The v2 architecture already required supporting evidence, opposing evidence, kill conditions, and a first rejection risk. Those controls remain useful but can still inherit the human PM's original framing.

This layer adds two distinct defenses:

1. **Counter-thesis:** challenge the explanations already inside the thesis.
2. **Outside-graph discovery:** search for economically material variables omitted from the thesis representation.

This reduces the risk that Alpha Cycle Lab becomes a sophisticated confirmation-bias engine while avoiding the opposite failure mode of converting red-team output into another false-precision score.

## Next integration gate

After this contract is merged:

1. rebase/revalidate the parked certified forward-valuation PR against the new main;
2. preserve `Certified Expectation State → Forward Valuation State` fail-closed semantics;
3. add a separate price-implied expectation layer;
4. then begin the semiconductor causal engine and later Underwriter integration.
