# Research Request Intake v2.1

## Purpose

Research Request Intake is the first write-side operating surface for Alpha Cycle Lab's Research Observatory.

It records **what the human PM wants researched** before any investment conclusion exists. The resulting `AnalysisRequestSnapshot` is appended to a new immutable Research Run Ledger snapshot and appears in the Observatory as `request_pending`.

Request intake does not:

- create an investment thesis;
- infer missing evidence;
- run the end-to-end research-round orchestrator;
- create a target price;
- create a security score;
- size or optimize a portfolio;
- execute an order.

## Why request and execution are separate

The system needs to distinguish these facts:

1. the PM requested research;
2. the system successfully assembled the typed research package;
3. the package reached `ResearchRoundSnapshot`;
4. the prospective decision was registered for future scorekeeping.

Collapsing those events into one button would hide real research failures. A request can therefore exist with no completed run. The Observatory renders this honestly as `request_pending`.

A later processing step must either:

- bind the request to an exact orchestrated `ResearchRoundSnapshot`; or
- record explicit `pre_orchestration_blocked` evidence explaining why typed inputs could not be formed.

## Application service

`alpha_cycle.research_request_intake_v2_1.record_analysis_request(...)`:

1. loads the latest validated Research Run Ledger, if one exists;
2. constructs an `AnalysisRequestSnapshot` under the active v2.1 guardrail identity;
3. rejects duplicate `request_id` values in current history;
4. recomputes the complete ledger summary from immutable history;
5. persists the request content-addressed and immutable;
6. persists a new immutable ledger snapshot.

If ledger persistence fails after the new request file was created, the uncommitted request file is removed before the exception is propagated.

## Streamlit intake page

When the Observatory requirements are installed, launch the existing app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\apps\research_observatory.py
```

Streamlit discovers `apps/pages/1_Research_Request.py` as an additional page.

The page accepts:

- artifact root;
- request ID;
- one or more security IDs;
- PIT evaluation date;
- 60/120/250 trading-day horizon;
- prospective/replay mode;
- Fast/Deep requested lane;
- free-text research request;
- optional tags.

Pressing **Record immutable request** writes request metadata only. It does not run the research engine.

## CLI

The same operation is available without Streamlit:

```powershell
.\.venv\Scripts\python.exe -m alpha_cycle.research_request_cli `
  --evaluation-date 2026-08-23 `
  --horizon 120 `
  --securities 000660 005930 `
  --mode prospective `
  --lane deep `
  --request-text "Compare SK hynix and Samsung Electronics using the PIT framework." `
  --tags semiconductor first-live-round
```

The command prints request and ledger snapshot identities. Reloading the Observatory then shows both securities as `request_pending` until an execution record is added.

## Current operational boundary

This phase deliberately stops at request intake.

The next write-side milestone is a **Research Request Processor / Preflight** that consumes pending requests and does one of two things:

- assembles validated persisted typed research artifacts and calls the existing end-to-end orchestrator; or
- records structured pre-orchestration blockers such as a missing persisted `InvestmentThesisSnapshot`.

That processor must not treat the presence of an arbitrary JSON file as proof that typed research evidence exists. Persisted investment-domain objects require content-addressed typed validation before they can satisfy a blocker.

## Privacy

Request text is user-authored operating history and may contain private investment notes. Runtime artifacts remain under the private/local artifact root and must not be committed to the public repository.
