# Alpha Cycle Lab Agent Protocol

This file is the repository-level startup protocol for ChatGPT, Codex, and other coding/research agents working on Alpha Cycle Lab.

## 1. Mandatory startup order

Use one consistent startup sequence for every task.

### Step 1 — Repository-state check only

Before planning, verify:

- current `origin/main` / default-branch head;
- active issue / PR state relevant to the task;
- whether another session already produced valid work.

Do not infer product direction from this state check.

### Step 2 — Read canonical product documents

Read in this order:

1. `docs/ACL_PRODUCT_CHARTER.md`
2. `docs/ACL_MASTER_ROADMAP.md`
3. `docs/ACL_ARCHITECTURE.md`
4. `docs/ACL_INDUSTRY_ADAPTERS.md`
5. relevant subsystem / milestone documents for the task.

### Step 3 — Reconcile current state with the roadmap

Confirm whether the active issue / PR still matches the canonical product direction and whether the roadmap current-state section is stale.

### Step 4 — Inspect task-specific code / tests / evidence

Only then plan or implement.

Do not rely on chat memory, an old README, a legacy roadmap, or one subsystem document when canonical documents are available.

## 2. Source-of-truth precedence

For product direction and sequencing:

1. `ACL_PRODUCT_CHARTER.md`
2. `ACL_MASTER_ROADMAP.md`
3. `ACL_ARCHITECTURE.md`
4. `ACL_INDUSTRY_ADAPTERS.md`
5. newer explicitly approved subsystem specifications
6. historical / legacy documentation

For trust/security semantics, existing stronger PIT/provenance/replay/authority contracts remain binding unless a reviewed change explicitly supersedes them.

If canonical documents conflict materially, reconcile them in a reviewed change rather than silently choosing one.

## 3. Product identity

Alpha Cycle Lab is an **AI-native Point-in-Time Investment Research Operating System**.

The product is not a fixed-score replacement for frontier reasoning models.

Its architecture is:

```text
deterministic state / trust core
+ versioned adaptive research knowledge
+ AI research intelligence
+ human final decision authority
```

ACL may perform autonomous research work. The user remains final capital-allocation authority.

## 4. Product and subsystem version namespaces

ACL product releases use **R1, R2, R3...**.

Subsystems keep independent versions such as Decision System v2.1, Research Package v2.1, Forecast Tournament v2.1, or source/evidence schema versions.

Do not infer that ACL Product R1 supersedes a subsystem v2.1 because the number is smaller.

## 5. Development philosophy

- Complete a strong common research loop rather than a large collection of unrelated tools.
- Do not remove valuable functionality merely to make a release artificially small.
- Do not require every industry fact to be hard-coded before the core can be complete.
- Default industry-specific structure to **versioned research models / knowledge packs**.
- Add bespoke code only for reusable source protocols, deterministic calculations, or common orchestration that genuinely requires code.
- Use progressive evidence formalization: cited research context may support exploration at a lower authority level; recurring decision-critical evidence should be promoted toward structured / replayable / validated source contracts.
- Never let lower-maturity evidence impersonate decision-critical numeric authority.
- Opportunity discovery must be capable of surfacing research candidates beyond the security the user already named.
- Mature research rounds must expose contradiction, uncertainty, and missing evidence.
- Outcome learning should generate calibration evidence and prospective model revisions, not rewrite historical forecasts.
- Engineering integrity is necessary, but new hardening should protect a concrete research / replay / publication / forecast / authority boundary.

## 6. Twelve R1 capability boundaries

R1 aims to close these capabilities end to end:

1. Global Macro and Market Observatory
2. Cross-Asset / Capital-Flow and Universe Change Detection
3. Opportunity Discovery
4. Autonomous Research Planning
5. Adaptive Industry Research Models / Knowledge Packs
6. Company Earnings Transmission
7. Expectations, Revisions, Valuation, and Price-Expectation State
8. Catalyst, Technical, Flow, and Positioning State
9. Counter-Thesis and Blind-Spot Search
10. Prospective Forecast Tournament
11. Structured Research Synthesis Interface and Decision Ledger
12. Outcome Learning and Research-Model Evolution

Do not silently push a central capability into an indefinite later phase merely to claim R1 completion.

Later releases may deepen these capabilities.

## 7. Industry breadth and completion

ACL Product R1 completion is a **functional core** completion, not an encyclopedic coverage gate.

R1 must prove generality across heterogeneous reference domains and a cold-start domain without requiring a duplicate research platform.

Broad industry coverage is tracked separately as Coverage Release C1.

C1 should eventually cover the major-family catalog in `ACL_INDUSTRY_ADAPTERS.md`, primarily through reviewed operational knowledge packs plus reusable plugins where genuinely needed.

A model with unresolved critical blockers in material drivers is not operational merely because it can publish a partial fail-closed package.

## 8. Evidence semantics

Preserve at minimum the distinction between:

- observed source evidence;
- authoritative source evidence;
- cited research context;
- deterministic derived values;
- model assumptions;
- internal forecasts;
- provider estimates;
- human / PM judgment;
- retrospective analysis.

Subsystems may use different enum names but may not collapse these semantics.

Missing evidence must not become a fake neutral score.

## 9. Required trust principles

Preserve:

- Point-in-Time correctness;
- exact provenance where required;
- immutable/content-addressed artifacts where required;
- deterministic replay;
- source-specific semantic authority;
- independent upstream reconstruction where an authority claim requires it;
- fail-closed handling of missing/mismatched decision-critical evidence;
- semantic separation of facts, estimates, forecasts, assumptions, and judgment;
- prospective forecast immutability;
- no hindsight model selection;
- no stale successful state masquerading as the current valid state after a failed later attempt;
- no silent evidence-maturity escalation.

Never weaken a scientific/evidence gate merely to obtain a populated output.

## 10. Research-model rules

Before writing new industry-specific code, classify the change.

### Prefer a knowledge-pack change when it is about

- industry drivers;
- value-chain structure;
- causal hypotheses;
- company exposure;
- source selection;
- catalyst types;
- counter-thesis conditions;
- research questions.

### Prefer reusable code when it is about

- a recurring acquisition protocol;
- deterministic calculation;
- schema validation;
- PIT / replay;
- persistence;
- generic orchestration;
- a reusable computation whose correctness matters.

AI may propose a new research-model version but must not silently overwrite an operational historical version.

## 11. Protected artifacts and local files

Unless an explicit later milestone authorizes a valid post-period evaluation, do not mutate the frozen SK hynix 2026Q3 prospective forecast / experiment artifacts.

Do not add, modify, stage, commit, or delete the user-owned local-only files:

- `config/company_exposures.local.yaml`
- `config/ecos_series.local.yaml`
- `config/security_mappings.local.yaml`

## 12. Implementation protocol

For implementation milestones:

```text
audit
→ implement
→ adversarial regression tests
→ focused tests
→ Ruff
→ strict mypy
→ full pytest
→ real / writer-backed acceptance where applicable
→ exact-head CI
→ self-audit
→ fresh exact-head review
```

If a fresh review finds a concrete valid P1/P2:

```text
fix
→ regression
→ sibling-path audit
→ rerun gates
→ fresh exact-head review
```

Repeat until the required merge gate is clean.

Do not merge merely because CI is green.

## 13. Scope discipline

Do not create functionality solely because it is architecturally interesting.

Every significant change should map to at least one of:

- a defined R1/R2/R3 capability;
- a Coverage Release goal;
- a real source / evidence gap;
- a real research-model need;
- a concrete trust defect in a live research path;
- a production/replay defect.

Examples:

- do not build portfolio execution to compensate for missing research evidence;
- do not add unrelated sources without a research question or recurring driver;
- do not proliferate one-company platforms when a shared runtime applies;
- do not hard-code narrative reasoning that belongs in the AI research layer;
- do not postpone central opportunity-discovery / counter-thesis value indefinitely behind infrastructure work.

## 14. Documentation change control

A material change to:

- ACL product purpose;
- ACL / AI / user role split;
- R1 capability boundaries;
- product / coverage release definitions;
- research-model architecture;
- evidence maturity policy;
- trust boundaries;
- completion criteria

must update the relevant canonical document(s) in the same reviewed repository change.

Do not rely on chat memory as the only record of an architecture decision.

## 15. New-session recovery protocol

When the user opens a new conversation and asks to continue Alpha Cycle Lab:

1. perform the repository-state check from Step 1;
2. read the four canonical documents in order;
3. verify current issues / PRs / main against the roadmap;
4. continue the active milestone without asking the user to restate the entire project unless a genuine product decision is unresolved.

Chat history and memory are useful context. The repository is the durable source of truth for ACL direction.
