# Research Run Ledger / Observability v2.1

## Purpose

The Research Run Ledger makes Alpha Cycle Lab's research process observable without adding a new investment-decision model.

It records:

- what research was requested;
- which securities, evaluation date, horizon, mode, and lane were requested;
- whether the request reached the typed end-to-end research-round orchestrator;
- the exact immutable `ResearchRoundSnapshot` identity when orchestration succeeded;
- structured blockers when research failed before or inside orchestration;
- whether an opportunity set, expectation overlay, or prospective scorekeeping registration existed;
- descriptive research-process statistics across immutable requests/runs.

It does **not** infer predictive skill, investment alpha, fair value, target price, position size, portfolio weights, or execution actions.

## Why this layer exists

Decision System v2.1 already has strong typed domain contracts. The missing operating layer was historical observability.

Without a run ledger, a dashboard can only show the latest object. It cannot answer questions such as:

- Why was `000660` blocked last week?
- Which blocker disappeared in the next research round?
- How often do requests fail before a typed thesis exists?
- How many rounds reach a complete opportunity set?
- How many prospective rounds are actually registered for future scorekeeping?

The ledger turns those questions into deterministic queries over append-only artifacts.

## Two execution kinds

### `orchestrated`

A real `ResearchRoundSnapshot` exists and is bound to the exact request.

The binder requires exact equality for:

- mode;
- evaluation date;
- 60/120/250 trading-day horizon;
- ordered security universe;
- v2.1 guardrail evidence identity.

For prospective runs, the round cannot predate the request that caused it. Replay may reconstruct an older point-in-time cutoff after the current request, so that chronology rule is intentionally different.

### `pre_orchestration_blocked`

The request could not even form the typed inputs required by the orchestrator.

Example:

- no persisted PIT `InvestmentThesisSnapshot` exists for a requested security.

This state is important. Silently dropping these requests would make the research process look healthier than it was and would prevent the UI from explaining the real bottleneck.

A pre-orchestration blocked run:

- requires at least one explicit structured blocker;
- cannot claim a `ResearchRoundSnapshot`;
- cannot claim an opportunity set, expectation overlay, or prospective registration.

## Immutable request object

`AnalysisRequestSnapshot` freezes:

- request ID;
- request timestamp;
- evaluation date;
- horizon;
- security IDs;
- prospective/replay mode;
- requested Fast/Deep lane;
- request text;
- guardrail evidence identity;
- optional tags.

The request text is an operating-history field, not an investment-evidence source. Production users should treat persisted request artifacts as potentially private user content and keep runtime artifact storage out of a public repository.

## Immutable run object

`ResearchRoundRunSnapshot` freezes:

- request identity;
- run identity;
- start/end timestamps and deterministic duration;
- mode/lane/evaluation date/horizon/security universe;
- exact research-round snapshot identity when present;
- round status;
- blockers and flags;
- opportunity-set snapshot identity;
- expectation-overlay snapshot identity;
- prospective-registration snapshot identity;
- guardrail evidence identity.

Copied fields exist for observability only. Normal construction should use `bind_orchestrated_run(...)` or `build_pre_orchestration_blocked_run(...)` rather than hand-assembling a run.

## Research-process observability

`ResearchProcessObservabilitySummary` currently reports descriptive process statistics:

- request count;
- run count;
- orchestrated vs pre-orchestration-blocked counts;
- blocked-run count;
- prospective vs replay counts;
- prospective-registered count;
- opportunity-set count;
- expectation-overlay count;
- unique researched securities;
- mean/median blockers per run;
- mean/median run duration;
- status frequencies;
- blocker-component frequencies;
- blocker-code frequencies.

These metrics answer **"is the research process becoming more complete and operational?"**

They do not answer **"is the investment system becoming more accurate or profitable?"**

## Learning boundary

The payload explicitly keeps the following disabled:

- predictive-skill inference;
- forecast-calibration claims;
- investment-alpha claims;
- decision-quality composite scores;
- weighted-score training;
- portfolio optimization;
- automatic execution.

Forecast and investment-decision learning require prospective outcomes from the already separate scorekeeping, attribution, and competence ledgers. A dashboard must show insufficient evidence rather than manufacture a performance percentage from a few outcomes.

## Persistence

Requests, runs, and ledger snapshots are content-addressed and immutable.

Persistence uses exclusive creation and refuses overwrite. A new history state creates a new ledger snapshot; an old ledger snapshot is never rewritten.

Recommended runtime directories:

```text
<artifact-root>/analysis_request_v2_1/<sha256>.json
<artifact-root>/research_round_run_v2_1/<sha256>.json
<artifact-root>/research_run_ledger_v2_1/<sha256>.json
```

Runtime artifacts should generally remain local/private even when the source repository is public.

## UI contract

The future Streamlit Research Observatory should be a read-side adapter over this ledger and existing typed domain snapshots.

The UI may display:

- Research Inbox;
- latest run by security;
- blocker inspector;
- analysis history;
- process observability;
- opportunity-set / expectation-overlay availability;
- later, prospective outcome and competence views.

The UI must not recreate valuation thresholds, ranking formulas, thesis logic, or investability decisions inside Streamlit code.

## Next step

After this ledger is merged:

1. add a thin read-side application service that validates persisted ledger JSON;
2. build the Streamlit Research Observatory on that service;
3. start recording real prospective research requests/runs;
4. activate predictive-learning views only as genuine prospective outcomes accumulate.
