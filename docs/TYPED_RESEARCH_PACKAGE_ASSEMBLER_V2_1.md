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

The package assembler treats persisted state as untrusted input until it is revalidated. The component repository scans immutable snapshot directories and validates:

1. the complete persisted payload hash against the declared `snapshot_id`;
2. typed reconstruction against the same content identity;
3. exact schema-v1 manifest fields and safety flags;
4. manifest-to-payload identity and metadata agreement;
5. canonical `<UTC timestamp>__<snapshot-id-prefix>` directory identity;
6. duplicate snapshot identities;
7. the mutable latest pointer, when present, against an actually validated immutable snapshot;
8. `captured_at <= research_cutoff_at` before a snapshot becomes PIT-selectable;
9. repository, snapshot, payload, manifest and pointer containment with symlink rejection;
10. reader-CWD-independent relative-pointer normalization.

The thesis and preflight repositories are also containment-checked before use. A missing `artifact_root` beneath a symlinked ancestor is rejected before any lock or publication can create directories through the alias.

Unknown payload fields therefore change the raw content address rather than being silently ignored. Unknown manifest or pointer fields fail closed under the schema-v1 contract.

## Request, PIT and cross-component binding

Assembly requires the current #301 thesis-preflight state to be present, typed, bound to the exact request, and ready. The mutable preflight selection must satisfy:

`research_cutoff_at <= selected_at <= processed_at`.

If a thesis selected by that ready preflight is no longer reconstructable, the failed assembly is persisted as a structured current package blocker instead of leaving the Observatory at a stale `pre_orchestration_ready` state.

Per security, selection requires the request-compatible:

- thesis/security/horizon;
- underwriting thesis/security/evaluation-date/lane/guardrail;
- payoff thesis/security/horizon/guardrail;
- Decision View security/evaluation-date/guardrail;
- Expectation Gap bound to the selected Decision View, security, evaluation date, guardrail and target variable/date/unit.

Persisted builder outputs are additionally checked for canonical invariants that their dataclasses alone do not enforce. Derived evidence is accepted only when its persisted source contracts can also be reconstructed and the owning canonical builder reproduces the exact derived snapshot:

- `ValuationEvidenceSnapshot + ExpectationStateSnapshot -> ForwardValuationStateSnapshot` is replayed through `build_forward_valuation_state(...)`;
- `ValuationEvidenceSnapshot + ValuationReferenceFrameSnapshot -> PriceImpliedRequirementSnapshot` is replayed through `build_price_implied_requirement(...)`;
- `InvestmentThesisSnapshot + CounterThesisSnapshot + BlindSpotDiscoverySnapshot -> EpistemicDefensePackageSnapshot` is replayed through `build_epistemic_defense_package(...)`;
- terminal theses cannot enter a ready package;
- thesis/payoff/underwriting and Decision View/Expectation Gap capture ordering is causal;
- ready underwriting carries the complete active lane-specific required-element set;
- a comparable forecast tournament contains at least two unique forecast identities with consistent distinct-forecaster/dependency counts;
- each persisted forecast registration is reconstructed as a canonical `ForecastRegistrationSnapshot`, and the reconstructed canonical payload must exactly match the persisted payload before tournament use;
- the selected forecast `(snapshot_id, forecast_id)` is the exact paired identity in that tournament;
- forecast `information_cutoff` cannot postdate the Decision View capture;
- the persisted Decision View selection rule is content-address validated, reconstructed as a canonical typed rule, preregistered before every tournament forecast, and required to resolve uniquely to the selected forecaster identity;
- consensus observations cannot postdate the Korea-local evaluation date;
- expectation-gap observation values, units and arithmetic remain bound to the selected Decision View.

## Fail-closed orchestration

If a required component is absent or incompatible, the assembler records a schema-v1 `PRE_ORCHESTRATION_BLOCKED` run with structured package blockers. Repeating the exact blocker state is historically idempotent while a newer operational preflight state can still produce a fresh blocker run so the Observatory does not hide a current package failure.

The assembler calls `run_research_round(...)` only after every requested security has a complete typed package. The orchestrator remains authoritative for opportunity-candidate, opportunity-set and research-round construction. A package being complete does **not** imply an investable or even non-blocked research-round result.

## Publication transaction

Generated opportunity candidates and the opportunity set are persisted and validated before round/run/ledger publication. Existing deterministic opportunity artifacts are fully checked against the generated payload, content address and canonical manifest before reuse.

All opportunity/round/run/ledger output repositories and pointer paths are checked for symlink and containment escapes before writes. Pre-existing deterministic round/run/ledger final paths are rejected before the legacy writers are invoked, preventing destructive collision cleanup.

Opportunity rollback is ownership-aware and monotonic. Mutable pointer replacement and rollback deletion atomically claim the current pathname into an unpredictable same-directory quarantine before validating its version; publication/restoration uses no-replace links, so a direct concurrent publisher that recreates the canonical name always wins. Round/run rollback uses the same claim-before-delete rule and therefore cannot unlink a foreign replacement after a separate ownership check. Immutable snapshot directories are removed only when this publication call created them and ownership remains exclusive. Publication remains ledger-last. Publication ownership is recorded only from a successful no-replace link or conditional replacement; equal bytes from a competing publisher never imply transaction ownership.

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

## Final hardening validation

The final review-hardening source commit `84ecd0360594826506873156a5eb464c856695c6` passed Ruff, mypy across 411 source files, and the full test suite with 1601 passed tests. Temporary hardening and diagnostic workflows/scripts were removed from that tested source commit before the normal pull-request CI retrigger.

## Frozen prospective artifacts

The SK hynix 2026Q3 prospective forecast/experiment artifacts are outside this milestone and must remain unchanged.