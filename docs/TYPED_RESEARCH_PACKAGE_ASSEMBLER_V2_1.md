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
8. `captured_at <= research_cutoff_at` before a snapshot becomes PIT-selectable;
9. resolved-root containment and rejection of symlinked component repositories, snapshot directories, files and pointers;
10. reader-CWD-independent normalization of persisted relative pointer paths.

The assembler additionally validates the investment-thesis repository root and its JSON entries before the thesis index is consumed. Symlinked or out-of-root thesis evidence fails closed.

Unknown payload fields therefore change the raw content address rather than being silently ignored. Unknown manifest or pointer fields fail closed under the schema-v1 contract.

## Request, PIT and cross-component binding

Assembly requires the current #301 thesis-preflight state to be present, typed, bound to the exact request, and ready. The PIT-selected thesis identities must still match the identities recorded by that preflight.

The operational preflight selection must satisfy:

```text
research_cutoff_at <= selected_at <= processed_at
```

Request security IDs are canonicalized at immutable intake, and legacy non-canonical IDs fail closed at assembly.

Per security, selection requires the request-compatible:

- thesis/security/horizon;
- underwriting thesis/security/evaluation-date/lane/guardrail;
- payoff thesis/security/horizon/guardrail;
- Decision View security/evaluation-date/guardrail;
- Expectation Gap bound to the selected Decision View, security, evaluation date, guardrail and target variable/date/unit.

The package also checks:

- terminal thesis states (`INVALIDATED`, `REPLACED`, `CLOSED`) cannot produce a package;
- thesis-derived capture order, including thesis before payoff/underwriting and referenced payoff before underwriting;
- Decision View capture before its derived Expectation Gap;
- Decision View target and tournament identity against underwriting;
- the exact parallel `(forecast_snapshot_id, forecast_id)` pair selected from the underwriting tournament;
- consensus-gap observation unit, selected decision value, observation timing, and absolute/relative arithmetic;
- price-implied gap decision-value conversion and arithmetic when price-implied observations exist;
- explicit underwriting references to payoff, expectation state and price-implied requirement against selected package objects where those references are present.

## Fail-closed orchestration

If a required component is absent or incompatible, the assembler records a schema-v1 `PRE_ORCHESTRATION_BLOCKED` run with structured package blockers.

Repeated identical package blockers remain idempotent only while no newer thesis-preflight selection has occurred. A newer preflight followed by another failed package assembly republishes current blocked operational state. Observatory preserves outstanding `typed_research_package_assembler_blocked` state across later thesis-preflight transitions; only a later package/orchestrated state may supersede it. A thesis-ready pointer may supersede only a blocker flagged `typed_thesis_preflight_blocked`.

The assembler calls `run_research_round(...)` only after every requested security has a complete typed package. The orchestrator remains authoritative for research logic. Package completeness does **not** imply an investable or non-blocked research-round result.

## Transactional publication

A completed orchestration is not published piecemeal as trusted state.

Before publication the assembler validates every output repository and deterministic path for containment and rejects symlinked artifact roots, opportunity repositories, round/run/ledger repositories, snapshot directories, pointer paths, rollback paths and final artifact slots.

Generated opportunity candidates and the opportunity set are persisted before the research round, run and ledger. If a deterministic opportunity directory already exists, its complete payload, content address and canonical manifest are validated before reuse. Newly persisted opportunity artifacts and pointers are revalidated before the round/run/ledger are committed.

Publication order is:

```text
opportunity candidates -> opportunity set -> research round -> run -> ledger
```

The ledger is published last. A downstream failure rolls back newly created opportunity directories, restores prior pointers, and removes newly published round/run artifacts. Rollback refuses to traverse symlinked snapshot directories.

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

Downstream orchestration additionally persists canonical opportunity candidate/set artifacts before the round/run/ledger.

`latest_*` JSON files are validated pointers only; they do not determine PIT selection.

## Frozen prospective artifacts

The SK hynix 2026Q3 prospective forecast/experiment artifacts are outside this milestone and must remain unchanged.
