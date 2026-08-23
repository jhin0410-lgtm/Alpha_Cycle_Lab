# Typed Investment Thesis Repository / Request Preflight v2.1

## Purpose

This milestone closes the first real operating gap between Research Request Intake and the end-to-end research-round orchestrator.

A recorded request is no longer forced to remain an unexplained `request_pending`. The system can now ask a narrower question:

> Does every requested security have a validated persisted `InvestmentThesisSnapshot` for the requested 60/120/250 trading-day horizon at the current preflight cutoff?

If not, the missing typed thesis is recorded as an explicit `PRE_ORCHESTRATION_BLOCKED` run in the Research Run Ledger.

## Typed thesis repository

`alpha_cycle.investment_thesis_repository_v2_1` adds content-addressed persistence and loading for the existing `InvestmentThesisSnapshot` contract.

The loader reconstructs all nested typed objects:

- `ThesisClaim` with `EpistemicStatus` and `ClaimDirection`;
- `CatalystClock`;
- all six `ThesisUncertainty` dimensions;
- `ThesisStatus`;
- forecast/scenario/evidence references and thesis lineage.

A JSON file is not accepted merely because it has the right filename. The declared snapshot identity, filename, reconstructed typed object, and canonical `snapshot_id` must agree.

Latest-thesis lookup uses embedded `captured_at`, snapshot lineage/version, and content identity. Filesystem modification time is never treated as research chronology. Future thesis snapshots are excluded from an earlier preflight cutoff.

Runtime path:

```text
<artifact-root>/investment_thesis_v2_1/<snapshot_id>.json
```

## Pending-request thesis preflight

`preflight_pending_request_theses(...)`:

1. acquires the shared Research Run Ledger write lock;
2. loads the newest validated ledger;
3. resolves the exact immutable analysis request;
4. finds the newest valid typed thesis for every requested security/horizon as of `processed_at`;
5. emits one structured blocker per missing security;
6. appends a `PRE_ORCHESTRATION_BLOCKED` run and a new immutable ledger snapshot when blockers changed;
7. avoids duplicating an identical blocker state on repeated preflight;
8. returns `ready_for_package_assembly=True` only when every requested thesis is present.

Passing this preflight **does not** mean the research round is ready or investable. It only means the thesis layer is available for the next typed package assembly step.

## Shared write serialization

Research request intake and preflight now use the same local lock:

```text
<artifact-root>/.research_run_ledger.lock
```

This prevents an intake writer and a processor writer from reading the same old ledger and creating competing append histories.

An existing lock fails closed. The system never silently steals a lock based on age.

## CLI

```powershell
.\.venv\Scripts\python.exe -m alpha_cycle.research_request_preflight_cli `
  --request-id <request-id>
```

The command reports resolved thesis snapshot identities, blockers, and whether history changed.

## Streamlit

Launch the existing Observatory:

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\apps\research_observatory.py
```

The multipage app now includes **Request Preflight**.

## Safety boundary

This milestone does not:

- author a thesis from thin evidence;
- fabricate missing research components;
- call the end-to-end orchestrator when only a thesis exists;
- infer `INVESTABLE_NOW`;
- create a target price;
- size a position;
- optimize a portfolio;
- execute a trade.

## Next milestone

The next step is a typed **Research Package Assembler** that validates persisted Underwriting Readiness, Payoff Surface, Decision View / Expectation Gap and related objects. Only when every required object is typed, content-addressed, PIT-compatible and request-compatible should it call the existing `run_research_round(...)` orchestrator.
