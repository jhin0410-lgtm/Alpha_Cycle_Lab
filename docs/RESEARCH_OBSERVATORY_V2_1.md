# Alpha Cycle Lab — Research Observatory v2.1

## Purpose

The Research Observatory is the first operating UI for Decision System v2.1.

It is a **read-only control room** over immutable Research Run Ledger artifacts. It exists to make the research system usable without weakening the point-in-time, provenance, and epistemic boundaries already enforced by the domain layer.

The Observatory does not contain investment logic. It does not:

- create or edit an investment thesis;
- substitute missing evidence;
- calculate target prices;
- calculate a weighted security score;
- infer `INVESTABLE_NOW`;
- size positions;
- optimize a portfolio;
- execute orders.

## Architecture

```text
Typed research / decision contracts
            │
            ▼
End-to-End Research Round Orchestrator
            │
            ▼
Research Run Ledger (append-only)
            │
            ▼
Validated read-side service
`alpha_cycle.research_observatory_v2_1`
            │
            ▼
Streamlit adapter
`apps/research_observatory.py`
```

The Streamlit application never reconstructs valuation, payoff, opportunity, or investability logic. It renders validated read models from the application service.

## Integrity boundary

`load_research_run_ledger(...)` validates a persisted ledger before the UI can use it.

Validation includes:

1. JSON can be decoded;
2. filename equals declared SHA-256 snapshot identity;
3. declared ledger SHA-256 equals the canonical persisted payload;
4. every request is reconstructed through `AnalysisRequestSnapshot`;
5. every run is reconstructed through `ResearchRoundRunSnapshot`;
6. child request/run snapshot identities are recomputed;
7. blocker structures and enums are reconstructed through typed contracts;
8. duration is recomputed from timestamps;
9. research-process summary is reconstructed and revalidated by `ResearchRunLedgerSnapshot`;
10. safety boundary flags must remain explicitly disabled.

The newest ledger is selected by embedded `built_at`, with snapshot identity as deterministic tie-breaker. Filesystem modification time is not treated as research chronology.

## Screens

### Research Inbox

Shows the latest operating state for each researched security:

- latest request time;
- latest completed run time;
- requested Fast/Deep lane;
- prospective/replay mode;
- current research state;
- blocker count;
- whether an opportunity set exists;
- whether an expectation overlay exists;
- whether a prospective scorekeeping registration exists.

A newer request without a completed matching run is shown as `request_pending` rather than silently falling back to the old state.

The Inbox is a **research-priority view, not a buy list**.

### Blocker Inspector

Displays structured blocker history:

- component;
- blocker code;
- security;
- detail;
- related snapshot identity when present;
- run and completion time.

This makes fail-closed behavior operationally useful. A missing typed thesis, consensus input, comparable forecast, payoff surface, or other required object remains visible rather than being neutralized.

### Analysis History

Shows append-only completed research runs with:

- request/run identity;
- completion time;
- PIT evaluation date;
- horizon;
- securities;
- lane;
- mode;
- state;
- blocker count;
- duration.

### Learning Observatory

The first version intentionally separates two meanings of learning.

#### Research-process learning — available now

The UI can display process observability already supported by the Research Run Ledger:

- request/run count;
- blocked-run count/share;
- prospective registration count;
- mean blockers per run;
- run duration;
- repeated blocker components/codes.

These metrics answer whether the research process is becoming more operationally complete.

#### Forecast / investment-decision learning — not inferred here

The UI explicitly refuses to manufacture a predictive-performance score from run history.

Accuracy, calibration, decision relevance, information gain, prospective opportunity regret, causal attribution, and regime/dependency-aware competence are owned by the separate prospective scorekeeping / decision ledger / attribution / competence contracts.

Until those genuine outcome records are connected to a later Observatory read model, this screen says that predictive learning is **not evaluated by the Research Run Ledger**.

## Local installation

From the repository root in PowerShell:

```powershell
cd "C:\Download\쿠쿠\coding\Alpha_Cycle_Lab"
.\.venv\Scripts\python.exe -m pip install -r .\requirements-observatory.txt
```

The requirements file installs the project in editable mode plus Streamlit. Streamlit is kept out of the core package dependencies so CI/research execution does not carry a UI dependency unless the Observatory is used.

## Artifact root

The UI defaults to:

```text
<repo>/.alpha_cycle_artifacts
```

You may point it elsewhere with an environment variable:

```powershell
$env:ALPHA_CYCLE_ARTIFACT_ROOT = "C:\path\to\private\alpha-cycle-artifacts"
```

Runtime artifacts can contain private user request text. Do not commit the artifact directory to the public repository.

## Launch

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\apps\research_observatory.py
```

Then use the sidebar to inspect or change the artifact root.

## Empty-state behavior

A new installation may have no persisted Research Run Ledger yet. The UI shows an explicit empty state rather than loading demonstration investment data or synthesizing a result.

That is expected until real requests/runs are recorded.

## Why there is no “Run Research Round” button yet

The first UI is deliberately read-only.

A write button would need an application-service mutation boundary that:

- creates an immutable `AnalysisRequestSnapshot` first;
- resolves typed PIT inputs;
- records pre-orchestration blockers when inputs are missing;
- invokes the existing orchestrator without duplicating its logic;
- persists request, run, round, and updated ledger consistently;
- preserves prospective chronology and explicit authorization boundaries.

That mutation service should be implemented before a Streamlit button is allowed to trigger research.

## Next UI increments

After the read-only Observatory is proven useful with real history:

1. add validated views for expectation gap, payoff surfaces, and Pareto opportunity sets;
2. add prospective outcome / decision / competence read models;
3. add a typed request-execution application service and only then enable a `Run Research Round` control;
4. add a grounded read-only Copilot over the same service interfaces;
5. add FastAPI only if another client actually requires a network API.
