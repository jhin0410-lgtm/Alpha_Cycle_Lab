# Alpha Cycle Lab Canonical Architecture

Status: **Canonical after merge**

This document defines the intended long-term architecture of Alpha Cycle Lab (ACL) under the Product Charter.

It is the system-level map used to prevent future work from drifting into either a brittle hard-coded investment oracle or an endless collection of one-off tools.

## 1. Architectural objective

ACL should combine four different strengths:

1. deterministic software for persistence, chronology, calculation, replay, and workflow;
2. versioned research knowledge for industry/company structure;
3. frontier AI for adaptive research and causal reasoning;
4. human authority for final investment decisions.

The durable loop is:

```text
External World
    ↓
Observation / Source Acquisition
    ↓
PIT / Provenance / Evidence Maturity
    ↓
Change Detection / Opportunity Discovery
    ↓
Research Planner
    ↓
Versioned Industry Research Model / Knowledge Pack
    ↓
Evidence + Company Transmission + Challenge
    ↓
Forecast / Tournament / Outcome State
    ↓
Structured Research Package
    ↓
GPT / Reasoning Model
    ↓
User Decision
    ↓
Decision Memory + Later Outcome
    ↓
Error Analysis / Prospective Research-Model Revision
```

## 2. Four architectural planes

### Plane A — Deterministic state and trust substrate

Code owns:

- source capture;
- point-in-time chronology;
- provenance;
- revision history;
- deterministic transforms;
- time-series storage;
- content identity where required;
- replay;
- authority gates where required;
- forecast / outcome persistence;
- decision ledger;
- workflow state and publication.

This plane is finite and should be shared across industries.

### Plane B — Research knowledge

Industry-specific knowledge should normally live in a **versioned declarative research model / knowledge pack**.

It describes:

- the industry's ontology and value chain;
- important drivers;
- company transmission paths;
- indicator roles;
- source requirements;
- catalysts;
- risks;
- counter-thesis conditions;
- unresolved questions;
- known failure modes.

The knowledge pack is not itself source evidence and is not immutable truth. It is a versioned research hypothesis that can improve prospectively.

### Plane C — Adaptive research intelligence

AI research agents may:

- detect that the current research model is insufficient;
- generate research questions;
- discover cited evidence;
- propose new drivers;
- propose new source integrations;
- construct alternate explanations;
- search for counter-evidence;
- propose a new knowledge-pack version;
- prioritize which uncertainty matters most.

AI-generated claims retain their evidence class. A reasoning model cannot upgrade its own prose into authoritative source evidence.

### Plane D — Decision and learning

The reasoning model and user consume the structured package.

ACL may persist:

- the package used;
- forecast state;
- thesis state;
- user action if recorded;
- rationale / invalidation conditions if recorded;
- later outcomes;
- error analysis;
- proposed future research-model changes.

Historical decisions and forecasts are never silently rewritten.

## 3. Evidence maturity model

A central scalability rule is **progressive formalization**.

Not every useful research fact requires a bespoke formal data adapter on first contact.

Conceptually, evidence can move through levels such as:

```text
L0 — cited research context
L1 — structured recurring observation
L2 — source-bound replayable provider evidence
L3 — independently validated decision-critical authority
```

Exact subsystem enum names may differ. The important rule is semantic separation.

### L0 — cited research context

Examples:

- an official speech;
- a company release or presentation not yet normalized;
- an industry association note;
- a source-backed web research finding.

It may inform hypotheses and research planning with explicit source citation and uncertainty.

It must not impersonate independently validated numeric authority.

### L1 — structured recurring observation

A repeated variable has normalized semantics and PIT timing but may not yet support every high-authority conclusion.

### L2 — source-bound replayable evidence

Provider-specific semantics and source replay are established.

### L3 — decision-critical authority

Where a conclusion requires strong numeric authority, upstream facts are independently validated under the relevant contract.

Examples may include actual filings, a certified estimate source, or validated share/capital-structure inputs.

## 4. Source promotion economics

ACL should promote evidence maturity based on research value.

A source deserves deeper integration when it is:

- repeatedly used;
- economically material;
- decision-critical;
- sensitive to PIT/revision semantics;
- difficult to verify manually each time.

One-off contextual research does not automatically require a new Python source adapter.

Conversely, a material recurring driver should not remain indefinitely as an unverifiable prose claim merely because web research is convenient.

## 5. Observation and source layer

Source acquisition should preserve enough context to answer:

- what was requested;
- what was returned;
- when it was captured;
- when it was legitimately available;
- which entity / security / industry / metric it actually describes;
- what the source does and does not attest.

A source adapter must not erase important distinctions such as:

- actual vs estimate;
- preliminary vs final;
- consolidated vs separate;
- spot vs contract;
- nominal vs real;
- raw vs adjusted market data;
- provider estimate vs internal forecast.

## 6. PIT, provenance, replay, and authority

Existing trust infrastructure remains a binding substrate.

Important distinctions:

```text
replayable bytes ≠ semantic authority
internally consistent arithmetic ≠ source authority
normalized snapshot ≠ independent evidence
AI citation ≠ certified numeric authority
```

Fail closed when a downstream conclusion explicitly requires stronger authority than the available evidence provides.

A lower-maturity evidence item may still exist in the package as research context if its semantics are labeled honestly.

## 7. Change Detection and Opportunity Discovery

ACL must do more than answer questions the user already asks.

The observation engine should compare current valid state with prior valid PIT states and surface measured changes such as:

- pricing acceleration / deceleration;
- inventory turns;
- utilization changes;
- CAPEX shifts;
- earnings growth / revision changes where authoritative;
- catalyst timing changes;
- relative-strength / breadth / flow changes;
- fundamental / market-state divergence;
- cross-asset or macro regime changes.

Opportunity discovery outputs **research candidates**, not automatic recommendations.

Each candidate should retain the measured reasons it was surfaced.

## 8. Research planner

The planner converts a detected change or user request into an explicit research plan.

A plan should identify:

- target industry / company / security;
- current research model version, if any;
- key questions;
- required drivers;
- evidence gaps;
- source maturity required for each question;
- expected transmission path;
- counter-thesis questions;
- relevant 3M / 6M / 12M horizons;
- whether a forecast should be registered.

The planner may decide that existing evidence is insufficient and request additional research instead of forcing a conclusion.

## 9. Industry Research Models / Knowledge Packs

The former concept of a heavy bespoke "industry adapter" is refined here.

An industry adapter should normally consist of:

```text
versioned research model / knowledge pack
+ shared core runtime
+ optional reusable source/computation plugins only where necessary
```

The pack should define industry semantics, not duplicate common infrastructure.

A cold-start domain can begin as an AI-proposed DRAFT pack, then progress through review and source binding.

No AI agent may silently overwrite an existing operational pack. Revisions produce a new version with rationale and evidence lineage.

## 10. Transmission graph

A research model may represent relationships such as:

```text
macro variable
→ industry demand / supply
→ price / utilization / mix / backlog
→ company volume / ASP / cost
→ revenue / margin / earnings
→ expectation revision
→ valuation / price expectation
```

Edges should be semantically classified where possible as:

- accounting identity;
- contractual / mechanical relationship;
- empirical / model relationship;
- research hypothesis;
- qualitative judgment.

This prevents a plausible narrative from silently becoming deterministic truth.

## 11. Company Earnings Transmission

Company-level research should preserve differences in:

- product mix;
- customer mix;
- geography;
- contract structure;
- backlog;
- capacity ownership;
- cost curve;
- hedging;
- working capital;
- balance sheet;
- accounting basis.

The common runtime should support reusable financial transformations, but company sensitivity assumptions remain explicit and versioned.

## 12. Expectations and Valuation

The research state should represent, where evidence supports it:

- provider estimates;
- estimate revisions;
- guidance;
- consensus;
- valuation inputs;
- price-implied requirements;
- expectation gaps.

The existing #307/#309 trust findings remain important examples: replayable KIS bytes are not automatically certified consensus, and missing share-count/capital-structure/forward-estimate authority must not be converted into fabricated valuation.

Research context may discuss market expectations qualitatively when source-backed, but the package must distinguish that from certified numeric consensus.

## 13. Catalyst, Technical, Flow, and Positioning State

Shared market-state services may include:

- relative strength;
- trend efficiency;
- realized volatility;
- drawdown;
- volume / liquidity;
- breadth;
- foreign / institutional flow where authoritative;
- positioning proxies where supportable;
- RSI and other timing indicators where useful.

Catalysts should be dated or windowed when possible and linked to an expected transmission path.

Structural long-term themes are not automatically near-term catalysts.

## 14. Counter-Thesis and Blind-Spot Engine

A mature research round must have an adversarial stage.

It should represent:

- supporting evidence;
- contradicting evidence;
- unresolved evidence;
- stale evidence;
- missing critical evidence;
- unexplained observations outside the active model;
- alternative causal explanations.

A blind-spot proposal should open a research question or model revision proposal. It must not promote an unexplained correlation directly into causal authority.

## 15. Forecast, Tournament, and Outcome Layer

Prospective forecasts should bind:

- target security / metric / period;
- forecast family / identity;
- exact input cutoff;
- feature/training cutoff where applicable;
- forecast value/range;
- model-selection rule;
- scoring rule;
- registration timestamp;
- exact input lineage.

#310/#311 provides the current prospective forecast-tournament foundation.

A knowledge pack does not need months of mature outcomes before becoming operational. If it emits a forecast, the generic forecast contract must be used correctly. Outcome history accumulates afterward.

## 16. Structured Research Package

The package is the primary interface between deterministic ACL state and frontier-model reasoning.

It should make clear:

- what is observed;
- what changed;
- what is derived;
- what is only research context;
- what is an assumption;
- what is a model/provider forecast;
- what is authoritative;
- what supports the thesis;
- what contradicts it;
- what remains unavailable;
- what the current research model version is;
- which catalysts fall inside 3M / 6M / 12M horizons;
- which dimensions are incomparable.

Missing evidence must not be converted into artificial completeness.

## 17. GPT / Reasoning-Model Interface

ACL should remain model-agnostic enough that a future stronger model can reuse historical research packages.

Reasoning models may:

- synthesize macro / industry / company meaning;
- compare scenarios;
- identify tensions;
- construct alternative hypotheses;
- compare opportunities;
- explain opportunity cost;
- propose what would falsify a thesis;
- propose new research-model versions.

Their reasoning output does not retroactively become source authority.

## 18. Decision Ledger

Where the user chooses to record a decision, the ledger may retain:

- decision timestamp;
- security / universe;
- research package identity;
- research-model version;
- thesis state;
- chosen action;
- key reasons;
- invalidation conditions;
- expected horizon;
- optional runtime portfolio context.

Prior cost basis may be stored descriptively but is not a privileged economic reason to continue a position.

## 19. Outcome Learning and Research-Model Evolution

Later evidence should be compared with what was known and forecast at the time.

Error analysis may ask:

- was source evidence missing or wrong?
- was an assumption wrong?
- was timing wrong?
- was the industry transmission model wrong?
- was company sensitivity wrong?
- did valuation / expectations dominate fundamentals?
- did a catalyst fail or move?
- did an untracked variable matter?

The result is calibration evidence and a **prospective new model proposal**.

Allowed automatic behavior:

- compute forecast errors;
- append authenticated outcomes;
- surface recurrent error patterns;
- propose a model change.

Not allowed without an explicit governed contract:

- rewriting historical forecasts;
- silently changing old model versions;
- declaring causality from a small sample;
- automatically optimizing portfolio decisions from sparse outcomes.

## 20. Cold-start domain path

For a previously unsupported domain:

```text
user request or opportunity candidate
→ research planner finds no operational model
→ AI proposes DRAFT research model
→ source / driver / transmission review
→ evidence collection and maturity classification
→ real company mapping
→ challenge stage
→ structured research package
→ version promotion if acceptance passes
```

The common core should not need to change solely because the industry is unfamiliar.

A new reusable source or computation plugin is acceptable when genuinely required.

## 21. Code vs. knowledge boundary

Default to **code** for:

- reusable acquisition protocols;
- deterministic calculations;
- schema validation;
- chronology / replay;
- persistence;
- generic orchestration;
- repeated transforms where correctness matters.

Default to **versioned research knowledge** for:

- industry drivers;
- value chains;
- hypotheses;
- indicator importance;
- catalyst types;
- company exposure maps;
- counter-thesis conditions;
- research questions.

Default to **AI reasoning** for:

- open-ended synthesis;
- novel hypothesis generation;
- source discovery;
- blind-spot search;
- contextual weighting;
- research prioritization.

This boundary is the primary defense against both infinite bespoke development and a shallow generic dashboard.

## 22. Publication integrity

Current state must be explicit and fail closed where required.

A failed newer run must not leave an older successful result silently masquerading as current.

Publication patterns should preserve:

- exact generation identity;
- appropriate atomicity;
- replayable lineage;
- no partial trusted state;
- no silent evidence maturity escalation.

## 23. External constraints

ACL cannot create data rights that do not exist.

Real-world limits include:

- paid consensus / estimate licensing;
- alternative-data access;
- provider API changes;
- incomplete historical PIT availability;
- real-time market-data restrictions.

The architecture must represent these limits honestly rather than treating missing data as an engineering bug that can always be solved with more code.
