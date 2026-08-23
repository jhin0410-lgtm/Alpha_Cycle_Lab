# Typed Investment Thesis Repository / Request Preflight v2.1

## Purpose

This milestone closes the first real operating gap between Research Request Intake and the end-to-end research-round orchestrator.

A recorded request is no longer forced to remain an unexplained `request_pending`. The system can now ask a narrower question:

> Does every requested security have a validated persisted `InvestmentThesisSnapshot` for the requested 60/120/250 trading-day horizon at the research cutoff?

If not, the missing typed thesis is recorded as an explicit `PRE_ORCHESTRATION_BLOCKED` run in the Research Run Ledger.

## Typed thesis repository

`alpha_cycle.investment_thesis_repository_v2_1` adds content-addressed persistence and loading for the existing `InvestmentThesisSnapshot` contract.

The loader reconstructs all nested typed objects:

- `ThesisClaim` with `EpistemicStatus` and `ClaimDirection`;
- `CatalystClock`;
- all six `ThesisUncertainty` dimensions;
- `ThesisStatus`;
- forecast/scenario/evidence references and thesis lineage.

A JSON file is not accepted merely because it has the right filename. The complete persisted payload excluding `snapshot_id` is hashed first, then the declared snapshot identity, filename, reconstructed typed object, and canonical `snapshot_id` must all agree. Unknown or silently ignored fields therefore cannot preserve the original content-addressed identity.

Thesis publication is atomic. Persistence writes and fsyncs a hidden non-JSON temporary file first, then atomically hard-links the completed bytes into the immutable `<snapshot_id>.json` path. A concurrent reader scanning `*.json` therefore sees either no new artifact or the complete artifact, never an empty or partially written JSON file. Existing final paths are not overwritten.

Latest-thesis lookup uses embedded `captured_at`, snapshot lineage/version, and content identity. Version 2+ snapshots are admitted only when the referenced parent artifact exists, matches the same thesis/security/horizon, and immediately precedes the child version. Within a thesis identity, duplicate versions or multiple successors from the same parent are rejected as forked append-only history instead of silently choosing one branch. Filesystem modification time is never treated as research chronology. Future thesis snapshots are excluded from an earlier research cutoff.

Runtime path:

```text
<artifact-root>/investment_thesis_v2_1/<snapshot_id>.json
```

## Pending-request thesis preflight

`preflight_pending_request_theses(...)` separates two clocks:

- `processed_at`: when the preflight operation actually runs and, if necessary, appends ledger history;
- `research_cutoff_at`: the PIT evidence cutoff used to select thesis artifacts.

Prospective requests default `research_cutoff_at` to `processed_at` and may not backdate the research cutoff before the request time. Replay requests require an explicit timezone-aware `research_cutoff_at`; that cutoff may precede the time the replay request was submitted, which allows honest historical reconstruction without admitting later thesis artifacts.

The preflight:

1. acquires the shared Research Run Ledger write lock;
2. loads the newest validated ledger;
3. resolves the exact immutable analysis request;
4. resolves and validates the request-appropriate research cutoff;
5. finds the newest valid typed thesis for every requested security/horizon as of that cutoff;
6. emits one structured blocker per missing security;
7. appends a `PRE_ORCHESTRATION_BLOCKED` run and a new immutable ledger snapshot when blocker state changed;
8. refuses to append blocker history unless `processed_at` is strictly later than the current ledger head;
9. preserves the replay cutoff in blocker-run flags so different historical replay cutoffs cannot collapse into one idempotent history event;
10. avoids duplicating an identical blocker state for the same effective cutoff;
11. returns `ready_for_package_assembly=True` only when every requested thesis is present.

Duplicate security IDs are rejected at new request intake, and preflight also deduplicates legacy request security IDs defensively before resolving theses or blockers.

Passing this preflight **does not** mean the research round is ready or investable. It only means the thesis layer is available for the next typed package assembly step.

## Shared write serialization

Research request intake and preflight use the same local lock. The shared implementation intentionally retains the pre-#301 filename so an already-running #300 intake process and new #301 code cannot acquire different locks during a rolling upgrade:

```text
<artifact-root>/.research_request_intake.lock
```

This prevents an intake writer and a processor writer from reading the same old ledger and creating competing append histories.

An existing lock fails closed. The system never silently steals a lock based on age.

## CLI

Prospective request:

```powershell
.\.venv\Scripts\python.exe -m alpha_cycle.research_request_preflight_cli `
  --request-id <request-id>
```

Historical replay request:

```powershell
.\.venv\Scripts\python.exe -m alpha_cycle.research_request_preflight_cli `
  --request-id <request-id> `
  --research-cutoff-at 2026-06-30T15:00:00+09:00
```

The command reports the effective research cutoff, resolved thesis snapshot identities, blockers, and whether history changed.

## Streamlit

Launch the existing Observatory:

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\apps\research_observatory.py
```

The multipage app now includes **Request Preflight**. Replay requests expose an explicit ISO-8601 PIT-cutoff field and fail closed if it is omitted or lacks a timezone offset.

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
