# Alpha Cycle Lab Industry Research Model / Knowledge Pack Standard

Status: **Canonical after merge**

This document defines the common contract for industry-specific research knowledge in ACL.

The historical term **industry adapter** remains for compatibility, but the preferred architecture is:

```text
Industry Research Model / Knowledge Pack
+ shared ACL core runtime
+ optional reusable source/computation plugins where genuinely needed
```

The goal is broad and deep industry research without turning every industry into a separate software project.

## 1. Purpose

A research model translates generic evidence into an industry-specific research structure.

It should help answer:

- what drives demand, supply, pricing, inventory, utilization, capacity, and investment;
- which indicators tend to lead, coincide with, or lag the cycle;
- how those changes transmit into company revenue, margins, cash flow, and balance-sheet outcomes;
- what expectations the market may already reflect where evidence is available;
- which catalysts matter at 3M / 6M / 12M;
- what evidence weakens the active thesis;
- what the current model does not explain;
- what evidence remains missing or too weak for a decision-critical conclusion.

The model should not merely restate textbook industry knowledge. Its value comes from giving ACL a structured way to observe the current state and revise the research model over time.

## 2. Default representation

Industry-specific research should default to **versioned declarative knowledge** rather than bespoke Python.

A knowledge pack may contain:

- industry ID / version;
- ontology / value-chain nodes;
- driver registry;
- source requirements;
- evidence maturity requirements;
- transmission edges;
- company exposure templates;
- catalysts;
- counter-thesis conditions;
- expected failure modes;
- unresolved research questions;
- supported forecast targets;
- pack-change history and rationale.

Use code only when the industry genuinely requires a reusable source protocol, deterministic calculation, or computation plugin not already provided by the common core.

## 3. Common research domains

Every operational model should address the following where economically applicable.

### 3.1 Macro exposure

Examples:

- policy rates / real rates;
- FX;
- inflation;
- liquidity / credit;
- fiscal policy;
- commodity inputs;
- tariffs / trade policy;
- geopolitics;
- subsidies / procurement regimes.

The model should explain why the variable matters rather than merely attaching a series.

### 3.2 Industry cycle

Common dimensions:

- demand;
- supply;
- price / spreads;
- inventory;
- utilization;
- capacity;
- CAPEX / investment;
- lead times;
- orders / backlog;
- competitive capacity additions / removals.

The pack should state which dimensions are relevant and why.

### 3.3 Company transmission

Typical path:

```text
industry demand / price / volume / mix / utilization / cost / backlog
→ company units / ASP / mix / input cost / delivery schedule
→ revenue
→ gross margin / operating margin
→ operating profit / net income / cash flow
→ balance-sheet / CAPEX / working-capital effects
```

Company sensitivity may differ by:

- product mix;
- customer mix;
- geography;
- contract structure;
- capacity ownership;
- cost curve;
- hedging;
- backlog;
- accounting basis.

Do not assume companies in one industry have identical exposure.

### 3.4 Expectations and valuation

Where evidence supports it, represent:

- provider estimates;
- estimate revisions;
- guidance;
- consensus;
- valuation inputs;
- price-implied requirements;
- disagreement between operating evidence and market expectations.

Authority is source-specific.

A replayable provider payload is not automatically a certified estimate or consensus source.

### 3.5 Catalysts

Recommended fields:

- event identity;
- security / industry scope;
- event date or window;
- known_at / available_at;
- source evidence;
- expected transmission channel;
- 3M / 6M / 12M relevance;
- dependencies and uncertainty.

A long-term theme is not automatically a near-term catalyst.

### 3.6 Market / technical / flow state

Shared measurements may include:

- relative strength;
- trend;
- realized volatility;
- drawdown;
- volume / turnover / liquidity;
- breadth;
- foreign / institutional flow where authoritative;
- positioning proxies where supportable;
- RSI or similar timing indicators.

These are supporting state and timing evidence, not independent fundamental authority.

### 3.7 Counter-evidence and uncertainty

A pack must support research states such as:

- `SUPPORTING`;
- `CONTRADICTING`;
- `UNRESOLVED`;
- `MISSING_CRITICAL`;
- `STALE`;
- `MEASURED_NON_DIRECTIONAL`;
- `NON_AUTHORITATIVE`;
- cited lower-maturity research context.

Do not force all evidence into bullish / bearish buckets.

### 3.8 Forecast support

The **ACL core** provides a generic prospective forecast contract.

An industry pack may declare supported forecast targets such as revenue, operating profit, price, utilization, capacity, or another economically meaningful metric.

A pack does not need months of matured outcome history before becoming operational.

If the pack emits a prospective forecast, it must use the generic forecast contract correctly, including exact cutoff, target definition, lineage, registration time, and scoring rule.

Outcome history accumulates after operational acceptance.

## 4. Driver registry

Each pack should maintain an explicit registry of important research drivers.

A driver may include:

- driver ID;
- economic meaning;
- unit / currency;
- source class;
- desired evidence maturity;
- expected frequency;
- PIT availability semantics;
- leading / coincident / lagging role if justified;
- linked transmission nodes;
- caveats;
- expected failure conditions;
- required / optional / exploratory status.

Adding a metric because it is available is not sufficient. It should answer a research question.

## 5. Evidence maturity requirements

For every material driver, the pack should state the minimum evidence maturity needed for different uses.

Example:

```text
Driver: DRAM contract price
- research discovery: cited official/industry source may be sufficient
- recurring cycle monitor: structured PIT observation preferred
- deterministic earnings bridge: exact unit/frequency semantics required
- decision-critical valuation input: stronger authority may be required
```

This prevents two opposite failures:

- blocking all useful research until every source has institutional-grade integration;
- treating a casual web citation as certified numeric authority.

## 6. Transmission map

Major edges should be classified where possible as:

- accounting identity;
- contractual / mechanical relationship;
- empirical / model relationship;
- research hypothesis;
- qualitative judgment.

Example:

```text
memory contract price
→ company ASP
→ revenue
```

may be economically important but still depends on product mix, contract timing, currency, and company-specific exposure.

The pack should preserve those caveats rather than promoting a plausible narrative into deterministic truth.

## 7. Pack lifecycle

Recommended lifecycle:

```text
DRAFT
→ REVIEWED
→ SOURCE_BOUND
→ OPERATIONAL
→ CALIBRATING
→ SUPERSEDED / DEPRECATED
```

### DRAFT

AI or human research structure exists but is not yet approved for operational research.

### REVIEWED

Core ontology, drivers, transmission hypotheses, and required evidence have been reviewed for obvious structural errors.

### SOURCE_BOUND

Material drivers have explicit source plans and evidence-maturity requirements. Not every source must already be L3 authority.

### OPERATIONAL

The pack can run a real PIT research round and produce a useful structured package without hiding unresolved critical blockers.

### CALIBRATING

`CALIBRATING` is a **post-operational subtype**, not a loss of operational status. A calibrating pack retains every `OPERATIONAL` acceptance requirement while prospective forecasts, outcomes, and model-version history accumulate. It therefore continues to count as operational coverage for C1 unless it is later `SUPERSEDED` or `DEPRECATED`.

### SUPERSEDED / DEPRECATED

A newer reviewed version replaced the pack or the old structure is no longer appropriate.

Old versions remain available for historical replay.

## 8. Operational acceptance

A pack may publish a partial fail-closed research package before it is operational.

However, a pack **must not** be declared `OPERATIONAL` while **any unresolved `MISSING_CRITICAL` item applies to a material driver required by the pack's stated operational research scope**. This is an unconditional operational blocker. If the intended research scope is narrowed so that the driver is no longer material, that narrowing must be an explicit reviewed model/pack revision with a new version and rationale; it cannot be treated as a waiver of the existing gap.

Operational acceptance requires:

- a reviewed research model version;
- real evidence sources for the material drivers needed by the target research question;
- explicit PIT cutoff;
- source/evidence maturity classification;
- at least one real company or security mapping where applicable;
- industry-to-company transmission that is useful rather than purely generic;
- support / contradiction / uncertainty representation;
- 3M / 6M / 12M horizon package where relevant;
- replay or reproducible source reconstruction appropriate to the evidence class;
- no silent missing-evidence neutralization;
- no unsupported authority promotion;
- no unresolved `MISSING_CRITICAL` blocker on any material driver within the stated operational research scope.

## 9. Change detection

A knowledge pack is not a static textbook.

A key output is **what changed relative to the prior valid research state**.

Examples:

- pricing acceleration / deceleration;
- inventory turning point;
- utilization inflection;
- CAPEX acceleration that may affect future supply;
- order / backlog change;
- estimate-revision acceleration where authoritative;
- catalyst entering / leaving a horizon;
- foreign / institutional flow divergence;
- improving fundamentals with weakening relative strength;
- company sensitivity changing after mix, capacity, contract, or balance-sheet changes.

## 10. Model revision and self-learning

Research models must evolve prospectively rather than mutate silently.

A revision proposal should include:

- parent model version;
- proposed change;
- reason for change;
- triggering evidence / forecast error / unexplained observation;
- affected drivers / edges / companies;
- expected improvement;
- risks of the new structure;
- effective date / research cutoff.

AI may generate the proposal.

Promotion to a new operational version requires the applicable review / source / PIT checks. The old version remains available for replay.

Outcome learning may support a change proposal, but a small sample does not automatically prove a new causal relationship.

## 11. Cold-start industry workflow

For a previously unsupported industry:

```text
research request or opportunity candidate
→ no operational pack found
→ AI drafts ontology / drivers / transmissions / sources / risks
→ human/agent review
→ source discovery and evidence classification
→ real company mapping
→ first real PIT research round
→ challenge / missing-evidence review
→ promote to OPERATIONAL only if acceptance passes
```

The common ACL core should not need a new bespoke platform solely because the industry is unfamiliar.

## 12. Reference-domain validation

The common research-model runtime must be tested on heterogeneous domains.

R1 reference acceptance includes:

- Memory Semiconductor;
- one policy/order/backlog-driven domain such as Defense/Aerospace;
- one long-cycle CAPEX/capital-goods domain such as Power Infrastructure or Shipbuilding;
- one cold-start domain not used to design the runtime.

This is a test of generality, not a permanent restriction on supported industries.

## 13. Coverage Release C1 catalog

Broad coverage remains an explicit project goal.

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

C1 coverage is complete when each major family has either:

- a reviewed `OPERATIONAL` or `CALIBRATING` pack with at least one real-data acceptance path and material drivers adequately source-bound; or
- an explicitly reviewed mapping to another `OPERATIONAL` or `CALIBRATING` pack where the economic structure is genuinely shared, with inherited acceptance documented.

Because `CALIBRATING` is post-operational, entering calibration does not remove a family's already earned operational C1 coverage.

Any unresolved `MISSING_CRITICAL` item on a material driver within the pack's stated operational scope prevents operational/calibrating coverage from satisfying C1.

Additional future sub-industries do not retroactively invalidate C1.

## 14. Pack vs plugin decision rule

Before writing new industry-specific code, ask:

1. Is this difference primarily **knowledge / ontology / hypothesis / source selection**?  
   → put it in the pack.

2. Is this a genuinely new **acquisition protocol** used repeatedly?  
   → implement a reusable source plugin.

3. Is this a genuinely new **deterministic calculation** whose correctness matters across research rounds?  
   → implement a reusable computation plugin.

4. Is this only a one-off interpretation or hypothesis?  
   → keep it in AI research output / model proposal rather than permanent code.

This rule is the main mechanism that prevents industry breadth from becoming infinite bespoke software development.
