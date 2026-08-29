# Alpha Cycle Lab Product Charter

Status: **Canonical after merge**

This document defines what Alpha Cycle Lab (ACL) is, what it is not, who owns each class of decision, and what must remain true when the architecture evolves.

When another roadmap, chat history, README, subsystem document, or implementation detail conflicts with this charter, this charter controls product direction unless a later reviewed charter explicitly supersedes it.

## 1. Product definition

Alpha Cycle Lab is an **AI-native Point-in-Time Investment Research Operating System**.

ACL exists to give a human investor and frontier reasoning models capabilities that an ad-hoc chat workflow does not reliably provide:

- persistent observation of markets and research variables;
- point-in-time memory of what was actually knowable;
- reproducible calculations and historical state;
- systematic change / inflection / divergence detection;
- explicit company and industry transmission models;
- structured counter-evidence and blind-spot search;
- prospective forecast registration and later outcome evaluation;
- durable decision and research history;
- a structured evidence package that can be re-used by better future reasoning models.

ACL is allowed to perform autonomous **research work**. It is not the final autonomous capital-allocation authority.

The intended decision chain is:

```text
real-world evidence
→ ACL deterministic state / research memory
→ adaptive research models and AI research agents
→ structured research package
→ GPT or another strong reasoning model synthesizes
→ user makes the final investment decision
→ decision and forecast history are preserved
→ later outcomes update research memory prospectively
```

## 2. The key design constraint

ACL must satisfy both of these conditions:

1. **It must do materially more than a one-off GPT conversation.**
2. **It must not require a person to hard-code the entire investment world.**

Therefore ACL is not a giant library of hard-coded investment rules. It is a finite research engine operating on an extensible, versioned knowledge layer.

A new industry should normally require a new or updated research model / knowledge pack, not a new research platform.

## 3. Four responsibility layers

### 3.1 Deterministic ACL core

Software is responsible for tasks where deterministic execution, persistence, calculation, and auditability are valuable:

- source acquisition and capture;
- Point-in-Time chronology;
- provenance and revision history;
- deterministic calculations and transformations;
- time-series state and change detection;
- current-state and historical-state persistence;
- source-specific authority checks where required;
- forecast preregistration and immutable outcome history;
- decision ledger and research history;
- workflow orchestration and replay.

### 3.2 Adaptive research knowledge layer

Industry and company research structure lives primarily in **versioned research models / knowledge packs**, not bespoke Python implementations.

A research model may define:

- industry ontology and value chain;
- demand, supply, pricing, inventory, utilization and CAPEX drivers;
- company transmission paths;
- leading / coincident / lagging indicators;
- source requirements and evidence priorities;
- catalysts;
- structural risks;
- counter-thesis conditions;
- expected failure modes;
- research questions and unresolved gaps.

Strong reasoning models may propose new models or revisions. Those changes must be versioned and evidence-linked rather than silently rewriting history.

### 3.3 AI research intelligence

GPT or another strong research/reasoning model is used where flexible interpretation has higher value than fixed software logic:

- macro and industry interpretation;
- hypothesis generation;
- causal synthesis;
- research planning;
- alternative explanations;
- blind-spot search;
- counter-thesis generation;
- scenario construction;
- cross-industry comparison;
- deciding which evidence deserves deeper formalization;
- proposing changes to research models.

ACL should not reimplement frontier-model reasoning as brittle fixed scores merely because it can be expressed in Python.

### 3.4 User decision authority

The user remains the final authority for:

- buy / hold / add / reduce / exit / replace / cash decisions;
- portfolio concentration and risk tolerance;
- acceptance or rejection of AI-generated reasoning;
- material causal-model changes when human approval is required;
- any eventual real-money execution authorization.

Real-account autonomous trading is not a current product requirement.

## 4. Core functional capabilities

ACL product-level **Release R1** targets a finite closed research loop with these twelve capabilities:

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

These are capability boundaries, not promises that every data source or every industry is complete forever.

## 5. Completion is functional, not encyclopedic

ACL is not complete when it knows every industry fact in existence.

ACL R1 is functionally complete when the common system can:

```text
observe a defined universe
→ detect a material change
→ open a research question
→ load or create a versioned research model
→ identify evidence requirements
→ obtain and classify available evidence
→ connect industry changes to company economics
→ expose support, contradiction, uncertainty, and missing evidence
→ preserve prospective forecasts where applicable
→ produce a GPT-consumable 3M / 6M / 12M research package
→ record the user decision when requested
→ later evaluate forecasts / assumptions against outcomes
→ propose a prospective research-model update
```

and can perform a **cold-start acceptance on a previously unsupported research domain without changing the common core**, except where a genuinely new source protocol or deterministic calculation requires a reusable plugin.

New industries, sources, and indicators after that point are coverage and capability upgrades, not proof that the core was never complete.

## 6. Broad coverage remains a real product goal

Functional completion does not mean intentionally narrow coverage.

ACL should ultimately maintain research-model coverage across the major investable industry families relevant to the user. Broad coverage is tracked as a separate **Coverage Release** so that:

- the core can have a real completion state;
- industry breadth can still be completed systematically;
- adding another sub-industry does not reopen the definition of the core product.

The initial major-family coverage catalog is maintained in `docs/ACL_INDUSTRY_ADAPTERS.md`.

## 7. Progressive evidence formalization

A personal research system cannot economically build a bespoke first-party adapter for every fact before using it.

ACL therefore supports multiple evidence maturity levels while keeping semantics explicit.

A typical progression is:

```text
research discovery / cited context
→ recurring structured observation
→ source-bound replayable evidence
→ decision-critical independently validated authority where required
```

Rules:

- lower-maturity evidence may inform research with explicit uncertainty;
- it must not masquerade as independently certified numeric authority;
- repeatedly important or decision-critical drivers should be promoted into structured source contracts;
- unsupported valuation, consensus, or forecast values remain blocked rather than invented.

This allows ACL to research broadly without weakening the existing trust model.

## 8. What ACL must not become

### 8.1 A second-rate copy of GPT

Do not hard-code common industry reasoning merely to reproduce what frontier models already understand.

### 8.2 A fixed weighted-score oracle

Do not create false precision such as:

```text
macro 20% + earnings 30% + valuation 20% + technical 30% = BUY 78/100
```

unless the weighting rule has a narrow, explicit, validated purpose.

### 8.3 A confirmation-bias machine

The system must preserve supporting, contradicting, unresolved, stale, and missing evidence. Research agents must be able to search beyond the current thesis and beyond the security the user already prefers.

### 8.4 A perpetual architecture project

Every product release and coverage release must define a finite acceptance boundary. Engineering integrity is a constraint on real research capability, not an independent infinite objective.

### 8.5 A silently self-modifying investment rule

Outcome learning may generate calibration evidence and proposed future model revisions. It must not rewrite historical forecasts or silently promote small-sample correlations into causal truth.

## 9. Non-negotiable epistemic principles

### 9.1 Point-in-Time correctness

Research for cutoff T may use only evidence legitimately available by T under the relevant source contract.

### 9.2 Provenance

Material evidence retains source identity, availability/capture timing, content identity, and lineage into derived research artifacts.

### 9.3 Replayability

Historical research state should be reproducible from frozen evidence without silently substituting current data.

### 9.4 Independent authority

A normalized or derived artifact cannot certify the authority of its own upstream facts merely because it is internally self-consistent.

### 9.5 Fail closed where authority is required

Missing, ambiguous, stale, mismatched, or non-authoritative evidence must not become a guessed value, neutral score, fabricated consensus, fabricated valuation, or fabricated payoff.

### 9.6 Semantic separation

At minimum distinguish:

- observed source evidence;
- authoritative source evidence;
- cited research context;
- deterministic derived value;
- model assumption;
- internal model forecast;
- provider estimate;
- human / PM judgment;
- retrospective analysis.

Subsystem-specific schemas may use different enum names but must preserve the distinction.

### 9.7 Prospective immutability

A prospectively registered forecast or experiment must not be rewritten after its target outcome becomes observable.

### 9.8 Technical analysis is supporting evidence

Relative strength, trend, volume, volatility, RSI, breadth, and flow may characterize timing and market state. They do not replace fundamental or industry analysis and do not become standalone directional truth without a validated model contract.

## 10. Common investment questions

ACL should help the reasoning layer answer:

1. What macro regime are we in?
2. Where is liquidity and capital moving?
3. Where is the industry in its cycle?
4. Which variables are changing now, and which are merely noisy?
5. How and when do those variables transmit into company revenue and profit?
6. Are earnings expectations likely to be revised?
7. What expectations are already reflected in price?
8. Which catalysts genuinely matter at 3, 6, and 12 months?
9. What evidence contradicts the current thesis?
10. What is unknown, stale, or non-authoritative?
11. Which other industries or securities deserve attention even if the user did not ask about them?
12. What did we believe before, what happened, and why were we right or wrong?

## 11. Product-level vs subsystem versioning

ACL product releases use the namespace **R1, R2, R3...**.

Existing subsystem versions such as **Decision System v2.1**, source-schema versions, evidence-contract versions, or forecast-protocol versions retain their own namespaces.

A product release does not supersede a higher-numbered subsystem version merely because its product release number is smaller.

Example:

```text
ACL Product Release R1
└── may contain Decision System v2.1
    + Research Package v2.1
    + Forecast Tournament v2.1
    + other independently versioned subsystems
```

## 12. Success criterion

ACL succeeds only if engineering integrity is converted into durable research advantage.

The intended advantage is not guaranteed excess return from software alone. It is a demonstrably stronger research process: broader observation, better temporal memory, less hindsight contamination, more explicit contradictions, reproducible calculations, reusable institutional memory, and increasingly calibrated future research.
