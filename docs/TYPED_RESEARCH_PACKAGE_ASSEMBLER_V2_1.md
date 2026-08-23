# Typed Research Package Assembler v2.1

## Purpose

This milestone connects the typed-thesis preflight to the existing Decision System v2.1 research-round orchestrator without inventing a second investment logic path.

The assembler answers a narrow operational question:

> For the exact immutable analysis request and its current PIT thesis-preflight cutoff, can every requested security be reconstructed from validated persisted typed research components?

Only a complete package may be delegated to the existing `run_research_round(...)` implementation.

## Required persisted components

Each requested security requires:

- `InvestmentThesisSnapshot`;
- `UnderwritingReadinessSnapshot`;
- `PayoffSurfaceSnapshot`;
- `DecisionViewSnapshot`;
- `DecisionExpectationGapSnapshot`.

The thesis is resolved through the content-addressed repository introduced in #301. The other four component families are reconstructed by `research_component_repository_v2_1` from their existing persistence formats.

## Trust boundary

The component repository does not trust a mutable `latest_*` pointer as evidence. It scans immutable snapshot directories and validates:

1. the complete persisted payload hash against the declared `snapshot_id`;
2. typed reconstruction against the same content identity;
3. exact schema-v1 manifest fields and safety flags;
4. manifest-to-payload identity and metadata agreement;
5. canonical `<UTC timestamp>__<snapshot-id-prefix>` directory identity;
6. duplicate snapshot identities;
7. the mutable latest pointer, when present, against an actually validated immutable snapshot;
8. `captured_at <= research_cutoff_at` before a snapshot becomes PIT-selectable.

Unknown payload fields therefore change the raw content address rather than being silently ignored. Unknown manifest or pointer fields fail closed under the schema-v1 contract.

## Request and cross-component binding

Assembly requires the current #301 thesis-preflight state to be present, typed, bound to the exact request, and ready. The PIT-selected thesis identities must still match the identities recorded by that preflight.

Per security, selection requires the request-compatible:

- thesis/security/horizon;
- underwriting thesis/security/evaluation-date/lane/guardrail;
- payoff thesis/security/horizon/guardrail;
- Decision View security/evaluation-date/guardrail;
- Expectation Gap bound to the selected Decision View, security, evaluation date, guardrail and target variable/date/unit.

The package also checks explicit underwriting references to payoff, expectation state and price-implied requirement against the selected package objects where those references are present.

## Fail-closed orchestration

If a required component is absent or incompatible, the assembler records a schema-v1 `PRE_ORCHESTRATION_BLOCKED` run with structured package blockers. Repeating the exact same package-blocker state is idempotent.

The assembler calls `run_research_round(...)` only after every requested security has a complete typed package. The orchestrator remains authoritative for opportunity-candidate, opportunity-set and research-round validation. A package being complete does **not** imply an investable or even non-blocked research-round result.

## Safety boundary

This milestone does not:

- fabricate missing evidence;
- author or mutate an investment thesis;
- infer `INVESTABLE_NOW`;
- create a target price;
- calculate optimal position size;
- create a portfolio recommendation;
- enable automatic execution.

The existing Decision System v2.1 guardrail evidence must match the request and all selected typed components.

## Persistence layout

The assembler consumes the existing writer layouts:

```text
<artifact-root>/underwriting_readiness/<timestamp>__<sha12>/...
<artifact-root>/payoff_surface/<timestamp>__<sha12>/...
<artifact-root>/decision_view/<timestamp>__<sha12>/...
<artifact-root>/decision_expectation_gap/<timestamp>__<sha12>/...
```

`latest_*` JSON files are validated pointers only; they do not determine PIT selection.

## Frozen prospective artifacts

The SK hynix 2026Q3 prospective forecast/experiment artifacts are outside this milestone and must remain unchanged.
