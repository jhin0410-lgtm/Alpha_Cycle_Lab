# Alpha Cycle Lab Master Roadmap

Status: **Canonical after merge**

This is the authoritative product roadmap for Alpha Cycle Lab.

Historical engineering plans remain useful background, but current product sequencing and completion criteria live here.

Read together:

1. `docs/ACL_PRODUCT_CHARTER.md`
2. `docs/ACL_MASTER_ROADMAP.md`
3. `docs/ACL_ARCHITECTURE.md`
4. `docs/ACL_INDUSTRY_ADAPTERS.md`

## 1. Version namespaces

ACL product releases use **R1, R2, R3...**.

Subsystems retain their own independent versions, for example Decision System v2.1, Research Package v2.1, Forecast Tournament v2.1, source-schema versions, and evidence-contract versions.

Product release numbering does not supersede subsystem numbering.

## 2. Current verified state — 2026-08-29

Current merged main:

`dfe3f204ac4b720f747df0851e05486fde36c399`

Major completed trust / decision-system milestones include:

- #303 — Typed Research Package v2.1
- #305 — Live Typed Research Round v2.1
- #307 — Provider-Specific Forward Estimate and Market Consensus Authority v2.1
- #309 — Replayable Valuation and Scenario/Payoff Authority v2.1
- #310 / PR #311 — Prospective Forecast Tournament and 3/6/12M Opportunity Set v2.1

#310 is closed and PR #311 was squash-merged on 2026-08-29 as main commit `dfe3f204ac4b720f747df0851e05486fde36c399`.

Important current authority state remains intentionally honest:

- real persisted market/OpenDART/ECOS replay infrastructure exists;
- 000660 and 005930 can produce exact-bound evidence-gated research states;
- KIS raw capture replay integrity does not imply authoritative numeric forward estimates or market consensus;
- current evidence does not establish the complete share-count/capital-structure/forward-estimate authority needed to activate normal valuation methods for 000660/005930;
- unsupported valuation, consensus, payoff, and expected-return dimensions remain blocked rather than guessed;
- the 000660/005930 x 3M/6M/12M opportunity acceptance can honestly publish no winner / no overall rank when evidence is insufficient;
- frozen SK hynix 2026Q3 prospective artifacts remain protected.

Current documentation milestone:

- Issue #312 / PR #313 — product charter, architecture, research-model standard, and durable roadmap.

Always verify current GitHub state before relying on this section.

## 3. Foundation — Trustworthy Research Substrate

Status: **substantially complete**

Existing foundations include:

- deterministic research infrastructure;
- persisted market and research sources;
- Point-in-Time chronology;
- provenance and content identity;
- canonical replay;
- source-authority boundaries;
- typed thesis / research packages;
- fail-closed handling of missing evidence;
- independent upstream reconstruction for important authority claims;
- prospective forecast immutability;
- exact-head CI and adversarial review discipline.

The foundation is not the end product.

New integrity work should normally be justified by a concrete research, replay, publication, forecast, or authority boundary. Do not create an unlimited parallel security project detached from investment-research value.

## 4. Product Release R1 — Functional Research Loop

Status: **next primary product release**

### Objective

Complete a stateful investment-research system that can discover changes, research them deeply, preserve what was known, challenge its own thesis, produce a structured package for GPT/user reasoning, and learn prospectively from later outcomes.

R1 targets all twelve core capabilities in the product charter. It does **not** require hard-coding all industries before the core can be declared complete.

### R1 capability map

1. **Global Macro and Market Observatory**
   - recurring macro / market state;
   - revision-aware observations;
   - regime-relevant changes.

2. **Cross-Asset / Capital-Flow and Universe Change Detection**
   - return / relative-strength / breadth / flow / earnings / event changes where data exists;
   - point-in-time comparisons with prior states;
   - no requirement that every signal be directional.

3. **Opportunity Discovery**
   - generate research candidates from a defined universe without requiring the user to name the security first;
   - explain which measured changes caused a candidate to be surfaced;
   - candidate generation is not a BUY recommendation.

4. **Autonomous Research Planning**
   - formulate research questions;
   - identify evidence gaps;
   - determine whether existing research models and sources are sufficient;
   - request deeper evidence or propose new model coverage.

5. **Adaptive Industry Research Models / Knowledge Packs**
   - versioned industry/value-chain structure;
   - driver registry;
   - source requirements;
   - transmission hypotheses;
   - catalysts / risks / counter-thesis;
   - AI may propose revisions; promotion is controlled and versioned.

6. **Company Earnings Transmission**
   - connect industry changes to volume / price / mix / cost / utilization / backlog / balance-sheet effects as economically applicable;
   - retain assumptions and timing lags explicitly.

7. **Expectations, Revisions, Valuation, and Price-Expectation State**
   - consume only evidence at the authority level actually established;
   - retain unavailable / incomparable states;
   - no fabricated consensus, valuation, payoff, or expected return.

8. **Catalyst, Technical, Flow, and Positioning State**
   - dated catalyst evidence;
   - horizon relevance;
   - relative strength / trend / volume / volatility / flows as supporting market state.

9. **Counter-Thesis and Blind-Spot Search**
   - mandatory challenge stage in mature research rounds;
   - search for contradicting evidence and unexplained observations;
   - propose alternative explanations or new research questions;
   - new correlations do not automatically become causal authority.

10. **Prospective Forecast Tournament**
    - existing #310/#311 foundation;
    - prospectively frozen candidates and selection rules;
    - authenticated later outcomes;
    - no hindsight mutation.

11. **Structured Research Synthesis Interface and Decision Ledger**
    - a GPT-consumable package that separates observed / derived / assumed / forecast / judgment / unavailable evidence;
    - optional user decision record with thesis, horizon, action, rationale, and invalidation conditions.

12. **Outcome Learning and Research-Model Evolution**
    - compare forecasts, assumptions, catalysts, and thesis paths with later outcomes;
    - decompose error where supportable;
    - propose a new research-model version prospectively;
    - never rewrite historical decisions or forecasts.

## 5. R1 sequencing

The exact issue numbers may change, but the product sequence should follow dependencies rather than arbitrary feature count.

### R1-A — Observable universe and change engine

Deliver:

- recurring macro / market / company observation state;
- prior-vs-current change detection;
- defined research universe;
- candidate surfacing with measured reasons.

### R1-B — Research planner and adaptive research-model runtime

Deliver:

- research-model / knowledge-pack schema and lifecycle;
- AI-assisted cold start for an unsupported domain;
- evidence requirements and source planning;
- model revision proposals with versioned diff and rationale.

### R1-C — Deep research transmission integration

Deliver:

- industry drivers;
- company transmission;
- expectations / valuation status;
- catalysts;
- technical / flow state;
- 3M / 6M / 12M structured evidence views.

### R1-D — Counter-thesis and blind-spot loop

Deliver:

- explicit adversarial research stage;
- unexplained-observation registry;
- alternate hypothesis generation;
- evidence-gap reopening when the active model does not explain new data.

### R1-E — Decision memory and outcome learning

Deliver:

- optional user decision ledger;
- later authenticated outcome linkage;
- error decomposition;
- prospective model-update proposal;
- retained forecast-tournament history.

### R1-F — End-to-end and cold-start acceptance

Prove the complete loop with real point-in-time evidence.

## 6. R1 reference-domain acceptance

R1 should not be validated only on one industry that shaped its design.

Use heterogeneous reference domains to prove the core is genuinely reusable.

Mandatory reference:

- **Memory Semiconductor** — cyclical technology / commodity-like pricing / mix / capacity / inventory.

Additional reference archetypes should include at least:

- one **policy / order / backlog-driven** domain such as Defense/Aerospace;
- one **capital-goods / long-cycle CAPEX** domain such as Power Infrastructure or Shipbuilding;
- one **cold-start domain** that was not used to design the common research-model runtime.

The cold-start domain is important: the system must be able to create and run a reviewed research model without modifying the common core solely because the industry is new.

A reusable source plugin or deterministic transformation may be added when the new domain genuinely requires new source or computation semantics.

## 7. R1 completion definition

ACL Product Release R1 is complete when one unchanged reviewed release satisfies all of the following:

1. all twelve core capabilities have real implementation paths rather than documentation-only placeholders;
2. the system can run a complete stateful research loop from observation through research package and later outcome learning;
3. opportunity discovery can surface a research candidate from a defined universe without the user naming it first;
4. a mature research round includes explicit counter-evidence / uncertainty / missing-evidence handling;
5. GPT or another reasoning model can consume the package without rebuilding source history manually;
6. decision-critical missing evidence remains blocked rather than neutralized;
7. the existing forecast tournament is integrated rather than bypassed;
8. at least the heterogeneous reference-domain acceptance set passes on real PIT evidence;
9. the cold-start domain does not require a bespoke duplicate research platform;
10. historical replay does not silently use future/current evidence;
11. model / knowledge-pack revisions are versioned and do not rewrite prior research states;
12. exact-head quality / regression / review gates are clean for implemented trust boundaries.

R1 completion does **not** require waiting months for every newly registered forecast to mature. The generic forecast contract and at least one legitimate scoring path must work; later outcome accumulation continues after R1.

R1 completion also does not require every major industry family to already have deep operational coverage. That is tracked separately below.

## 8. Coverage Release C1 — Broad Industry Knowledge Coverage

Status: **planned after the R1 research-model runtime is stable; may progress in parallel once the contract is stable**

### Objective

Build broad industry coverage without turning each industry into bespoke software.

Coverage is primarily delivered through reviewed **Industry Research Models / Knowledge Packs**, plus reusable source/computation plugins only where necessary.

Initial major-family catalog:

1. Semiconductor
   - Memory
   - Foundry / Logic
   - Equipment / Materials
2. AI / Data Center / Cloud Infrastructure
3. Power Grid / Electrical Equipment / Power Infrastructure
4. Defense / Aerospace
5. Shipbuilding / Marine
6. Construction / Infrastructure / Engineering
7. Automotive / Mobility
8. Batteries / Battery Materials
9. Telecom / Network Equipment
10. Industrial Automation / Robotics
11. Energy / Refining / Chemicals
12. Commodities / Metals / Resources
13. Financials
14. Consumer / Retail / Leisure
15. Biotech / Healthcare

C1 is complete when every listed major family has either:

- a reviewed operational research model with material drivers source-bound and at least one real-data acceptance path; or
- an explicit mapping to another reviewed operational model where the economic research structure is genuinely shared, with that mapping reviewed and the inherited acceptance documented.

An unresolved critical blocker in a material driver prevents that family/model from being declared operational even though a partial fail-closed research package may still be published.

Adding future sub-industries after C1 does not invalidate C1 completion.

## 9. Product Release R2 — Advanced Discovery and Research Autonomy

R1 already contains basic opportunity discovery, counter-thesis, and AI research planning because those capabilities are central to the product's value.

R2 deepens them rather than introducing them for the first time.

Potential R2 improvements:

- broader cross-country and cross-asset rotation detection;
- unexplained-residual / anomaly discovery across research models;
- automated source discovery and promotion proposals;
- richer alternative causal graph generation;
- more systematic cross-industry evidence comparison;
- research-budget prioritization based on uncertainty and potential decision impact;
- stronger agent orchestration for repeated research cycles.

## 10. Product Release R3 — Portfolio Decision Support

Objective:

Use trusted research and opportunity evidence with runtime portfolio state to support capital allocation.

Inputs may include:

- holdings, cash, and investable capital supplied at runtime;
- 3M / 6M / 12M opportunity evidence;
- macro / policy / geopolitical / industry-cycle overlap;
- catalyst timing;
- liquidity;
- supportable upside/downside or valuation evidence;
- opportunity cost.

Outputs may support:

- maintain;
- add;
- reduce;
- exit;
- replace;
- hold cash.

Cost basis and prior loss are descriptive, not privileged reasons to hold.

The user remains final decision authority.

## 11. Product Release R4 — Advanced Calibration and Research Evolution

R1 includes genuine outcome learning. R4 deepens statistical and longitudinal calibration once enough prospective history exists.

Possible improvements:

- indicator reliability by regime;
- forecast-family calibration history;
- systematic timing-error analysis;
- richer causal-model change evaluation;
- model-version performance comparison;
- controlled future selection-rule updates.

Do not manufacture significance from small samples.

## 12. Continuous production audits

Major releases should undergo cross-system audits covering:

```text
source
→ PIT
→ replay
→ observation
→ research model
→ company transmission
→ expectations / valuation
→ catalysts / market state
→ challenge / blind spot
→ forecast
→ research package
→ reasoning interface
→ decision memory
→ outcome learning
```

Audits should seek real trust breaks, stale state, authority escalation, hindsight leakage, silent missing-data normalization, and publication inconsistency.

## 13. Development economics

To remain realistic for a personal system:

- default to a declarative/versioned research model before bespoke industry code;
- create a reusable source adapter when a recurring decision-relevant source justifies it;
- allow cited research-context evidence at an explicitly lower authority level for one-off discovery;
- promote recurring important drivers toward structured/replayable authority;
- do not block all research until every possible source has institutional-grade integration;
- do not allow lower-maturity evidence to impersonate decision-critical numeric authority;
- prefer reusable platform capability over one-company special cases;
- do not remove valuable functionality merely to make a release smaller.

## 14. Protected state

Unless a later reviewed milestone establishes valid post-period evaluation, do not mutate the frozen SK hynix 2026Q3 prospective forecast / experiment artifacts.

Do not commit or mutate the user-owned local-only files:

- `config/company_exposures.local.yaml`
- `config/ecos_series.local.yaml`
- `config/security_mappings.local.yaml`
