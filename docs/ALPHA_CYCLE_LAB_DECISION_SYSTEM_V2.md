# Alpha Cycle Lab — Investment Decision System v2

## 1. Purpose

Alpha Cycle Lab is not a stock-price oracle, a generic quant score, an earnings-only forecasting lab,
or an automated trading engine.

Its purpose is to improve repeated capital-allocation decisions under uncertainty.

> **North Star**
>
> Detect changes in macro, industry, and company states before they are fully reflected in market
> expectations; verify how those changes transmit into earnings and valuation; identify the catalysts
> that can close the expectation gap; compare the payoff, uncertainty, timing, and opportunity cost of
> competing 3/6/12-month investments; allocate capital deliberately; and learn from realized outcomes
> without rewriting the original thesis after the fact.

Short form:

> **Find change → Find mispricing → Find catalyst → Compare payoff → Allocate → Learn.**

The system remains research/read-only. Human review owns the final investment decision.

---

## 2. What the system optimizes

### 2.1 Economic objective

The ultimate economic objective is **long-run capital growth**, not benchmark hugging and not a single
forecast-error metric.

However, Alpha Cycle Lab must not prematurely convert uncertain forecasts into a false-precision
portfolio optimizer. Until probability calibration is empirically defensible, the system should expose
rather than hide:

- expected upside and downside;
- time to catalyst and expected holding horizon;
- thesis confidence and evidence quality;
- model, regime, valuation, and catalyst uncertainty;
- liquidity and path risk;
- overlap with existing portfolio bets;
- opportunity cost versus the next-best candidate.

The v2 decision layer therefore uses **comparative opportunity ranking plus explicit risk constraints**.
It does not claim a mathematically optimal weight from uncalibrated probabilities.

### 2.2 Decision-quality objective

A high-quality decision is one where, using only information available at the decision timestamp:

1. the causal investment thesis is explicit;
2. the market expectation being challenged is explicit;
3. the expected path from state change to company economics is explicit;
4. the catalyst and horizon are explicit;
5. payoff and downside are estimated with uncertainty shown;
6. competing opportunities are considered;
7. invalidation conditions are frozen before the outcome;
8. sizing rationale is recorded separately from thesis quality;
9. the later outcome can be attributed to what actually worked or failed.

### 2.3 What is *not* the primary objective

The following are useful submetrics but must not become the project's North Star:

- one-quarter earnings MAE;
- one universal 0–5 company score;
- daily direction accuracy;
- headline sentiment accuracy;
- backtest CAGR without realistic point-in-time evidence;
- maximizing Sharpe ratio irrespective of the user's absolute-return mandate;
- maximizing the number of data sources, models, hashes, or validation checks.

Trust machinery is a constraint and research-enabling infrastructure, not the investment objective.

---

## 3. Alpha hypothesis

Alpha Cycle Lab is designed around three attainable forms of edge.

### 3.1 Analytical edge

Connect information that is individually public but economically fragmented:

```text
macro / policy / liquidity
        ↓
industry supply-demand / capacity / inventory / pricing
        ↓
company volume / price / mix / backlog / cost
        ↓
revenue / margin / earnings / cash flow
        ↓
consensus revisions and market expectations
        ↓
valuation and price response
```

The key question is not merely whether fundamentals improve, but whether the **magnitude, timing, or
persistence of improvement differs from what the market already discounts**.

### 3.2 Cycle-inflection edge

The system seeks transitions rather than static quality:

- excess inventory → normalization;
- underinvestment → supply scarcity;
- price decline → price stabilization → price increase;
- order slowdown → tender acceleration;
- utilization trough → operating leverage recovery;
- policy discussion → funded budget → contract → revenue recognition.

The system should distinguish early, middle, late, and declining phases of a cycle.

### 3.3 Time-horizon / behavioral edge

The preferred horizon is long enough for fundamentals and catalysts to matter but short enough to
reallocate when the thesis changes. The primary research horizons are:

- approximately 3 months / 60 trading days;
- approximately 6 months / 120 trading days;
- approximately 12 months / 250 trading days.

1/5/20-day outcomes remain useful for path and entry-timing analysis, but are secondary to the core
cycle/catalyst horizon.

---

## 4. Core architecture: a decision graph, not a linear score pipeline

The investment process is represented as a graph of claims and evidence.

```text
                         MARKET / POLICY STATE
                                  │
             ┌────────────────────┼────────────────────┐
             ↓                    ↓                    ↓
           MACRO              LIQUIDITY              FLOWS
             │                    │                    │
             └──────────┬─────────┴─────────┬──────────┘
                        ↓                   ↓
                  INDUSTRY CYCLE       PRICE / POSITIONING
                        │                   │
                        ↓                   │
                COMPANY TRANSMISSION       │
                        │                   │
                        ↓                   │
                   OUR FORECAST             │
                        │                   │
                MARKET EXPECTATION ─────────┘
                        │
                        ↓
                  VARIANT PERCEPTION
                        │
                        ↓
                  CATALYST / CLOCK
                        │
                        ↓
                    PAYOFF SURFACE
                        │
                        ↓
                 OPPORTUNITY SET
                        │
                        ↓
                PORTFOLIO ALLOCATION
                        │
                        ↓
                  REALIZED OUTCOME
                        │
                        ↓
            THESIS / FORECAST ATTRIBUTION
                        │
                        └──────────────→ LEARNING LOOP
```

No single edge is automatically causal merely because two series are correlated. Each important edge
must identify whether its status is:

- observed fact;
- accounting identity;
- economically motivated hypothesis;
- empirically validated relationship;
- unvalidated inference.

---

## 5. Three operating engines

### 5.1 Radar Engine — find where change is occurring

Question:

> **Where is the opportunity set improving or deteriorating now?**

The Radar narrows countries, industries, themes, and companies using:

- macro regime and changes in regime;
- fiscal and policy transmission;
- liquidity and FX conditions;
- sector and industry relative strength;
- supply, inventory, utilization, pricing, and capex inflections;
- orders, backlog, tenders, and funded demand;
- earnings-estimate revision breadth where certified;
- unusual but explainable flow/positioning changes.

Radar output is a **research-priority queue**, not a buy list.

A candidate must state why it surfaced now and the first reason it may be a false positive.

### 5.2 Underwriter Engine — test whether the thesis is economically investable

Question:

> **If the detected change is real, how does it become revenue, profit, cash flow, and ultimately
> shareholder return — and what does the market already price in?**

The Underwriter builds a thesis graph containing:

- key causal claims;
- supporting and opposing evidence;
- company-specific transmission path;
- internal forecasts and competing forecasts;
- consensus / expectation state;
- valuation state;
- dated or conditional catalysts;
- bull/base/bear payoff surfaces;
- uncertainty decomposition;
- explicit kill conditions.

The Underwriter must distinguish a **good company** from a **good investment at the current price and
current time**.

### 5.3 Allocator Engine — compare competing uses of capital

Question:

> **Given the current opportunity set and current portfolio, where should the next unit of capital go?**

The Allocator compares candidates on:

- expected payoff distribution, not only point target;
- downside and thesis-break downside;
- catalyst proximity;
- confidence and uncertainty;
- capital lock-up time;
- liquidity;
- overlap with existing macro/industry/factor bets;
- opportunity cost versus alternatives;
- whether the thesis requires adding, holding, reducing, replacing, or waiting.

Existing positions receive no special treatment because of cost basis. A held position must compete
with a fresh purchase at the current market price.

---

## 6. Sector-specific causal engines, common decision framework

A single universal company score cannot adequately model economically different industries.

Alpha Cycle Lab should use a common decision schema with sector-specific causal transmission models.

### 6.1 Semiconductors

Typical causal variables:

```text
end demand / AI capex
→ inventory / utilization
→ wafer capacity and technology migration
→ DRAM / NAND / HBM supply-demand
→ contract and spot pricing
→ bit shipment / ASP / product mix
→ gross margin / operating profit
→ estimate revisions
```

### 6.2 Defense

```text
geopolitics / defense budgets
→ funded procurement
→ tender / award probability
→ backlog
→ delivery schedule
→ revenue recognition
→ program margin / cash conversion
```

### 6.3 Shipbuilding

```text
fleet economics / LNG / regulation
→ ordering cycle
→ yard slot scarcity
→ newbuild price
→ orderbook quality
→ steel and labor costs
→ construction mix
→ revenue / margin recognition lag
```

### 6.4 Construction

```text
rates / housing / PF / policy
→ starts and project financing
→ domestic backlog and presales
→ overseas awards
→ input costs
→ construction progress
→ revenue / margin / cash flow
```

The sector engine defines what evidence matters. The common decision layer defines how evidence,
expectations, payoff, uncertainty, and opportunity cost are compared.

---

## 7. Thesis object as the central research unit

The primary research object in v2 is an **InvestmentThesis**, not a ticker score.

A thesis should minimally contain:

```text
thesis_id
as_of_timestamp
security_id
horizon
variant_view
why_now
market_state_claims[]
industry_claims[]
company_transmission_claims[]
market_expectation_claims[]
valuation_claims[]
catalysts[]
supporting_evidence[]
opposing_evidence[]
forecast_refs[]
scenario_refs[]
uncertainty
kill_conditions[]
first_rejection_risk
portfolio_overlap
opportunity_set_refs[]
status
```

Every material claim should bind to point-in-time evidence or be labeled as an explicit inference.

The thesis object must be append-only across decision timestamps. Later evidence can update thesis state,
but the system must preserve what was believed at the original decision time.

---

## 8. Market expectations are a first-class state variable

Fundamental improvement is not sufficient for an attractive investment.

The system must represent at least three views separately:

```text
OUR FUNDAMENTAL VIEW
        vs
MARKET / CONSENSUS VIEW
        vs
PRICE-IMPLIED VIEW
```

The investable edge is often the gap between them.

Required expectation capabilities, when source semantics are certified:

- point-in-time consensus revenue / operating profit / EPS;
- number and dispersion of estimates where available;
- estimate-revision history;
- guidance versus consensus;
- actual versus prior expectation;
- our forecast versus consensus;
- price-implied operating assumptions where valuation permits.

Uncertified KIS estimate fields remain evidence only and cannot silently become consensus.

---

## 9. Forecast Tournament — no single champion forever

Alpha Cycle Lab should not seek one permanent forecasting model.

For a material quantity, multiple predeclared forecasters can compete, for example:

- persistence benchmark;
- simple econometric model;
- industry-driver model;
- company operating model;
- certified market consensus;
- consensus plus a separately frozen proprietary overlay.

Each forecast records:

```text
forecast_id
forecast_origin
target
horizon
model_family
feature_evidence
training_scope
regime_tags
out_of_distribution_diagnostics
point_forecast
interval_or_scenario_range_if_predefined
actual_when_available
error_metrics
```

Later evaluation asks two questions:

1. Which forecaster was most accurate?
2. **Under what regime was each forecaster competent or incompetent?**

This creates a model-competence map rather than encouraging post-hoc model replacement.

### 9.1 Existing SK hynix 2026Q3 experiment

The currently locked SK hynix 2026Q3 company-gross-profit forecast remains an immutable prospective
experiment.

It must not be altered by v2 architecture work.

Its extreme standardized prospective input is recorded as an out-of-distribution diagnostic, not a
reason to redesign the frozen forecast after lock. The future Q3 outcome should score the frozen model
under the already-preregistered contract. Any successor model belongs to a separate research round.

---

## 10. Uncertainty is an output, not an inconvenience

A ranking that says `4.2 > 4.0` is incomplete if the first thesis is radically more uncertain.

Every material thesis should decompose uncertainty where possible into:

### 10.1 Evidence uncertainty

Are the source, definition, timestamp, and accounting/economic semantics reliable?

### 10.2 Forecast/model uncertainty

How unstable is the estimate across reasonable frozen models or assumptions?

### 10.3 Regime uncertainty

Is the current observation far outside the historical domain or occurring during a structural break?

### 10.4 Expectation uncertainty

How confidently do we know what the market already expects?

### 10.5 Catalyst uncertainty

Is the catalyst dated and contractually/officially defined, or merely narrative and open-ended?

### 10.6 Valuation uncertainty

How sensitive is payoff to multiple compression/expansion, terminal assumptions, or peer regime?

Uncertainty should affect research priority, scenario width, and position review. It must not be hidden
inside an arbitrary neutral score.

---

## 11. Payoff surface, not a single target price

For each investable thesis, the Underwriter should produce Bull/Base/Bear or another explicitly frozen
scenario set.

Each scenario should specify:

- macro/industry conditions;
- operating assumptions;
- earnings effect;
- catalyst path;
- valuation assumption;
- price or valuation range;
- likely horizon;
- path/downside risk;
- action if the scenario begins to materialize.

The system should also compute, where defensible:

- upside to scenario range;
- downside to bear range;
- break-even assumptions;
- time-adjusted opportunity cost;
- expected value only when scenario probabilities are evidence-based or explicitly subjective and
  preserved as such.

Do not fabricate precise probabilities merely to generate an expected return.

---

## 12. Opportunity ranking

The ranking layer compares **theses**, not companies in isolation.

A thesis can be:

- advance to underwriting;
- investable now;
- valuation-gated;
- catalyst-gated;
- evidence-gated;
- timing-gated;
- thesis weakening;
- invalidated;
- replaced by a superior opportunity.

A ranking record should show at minimum:

```text
candidate
horizon
variant_wedge
why_now
payoff_summary
downside_summary
uncertainty_summary
catalyst_clock
valuation_state
first_rejection
portfolio_overlap
opportunity_cost
next_action_for_human_review
```

No candidate advances solely because price recently rose or a popular theme was mentioned. There must
be a source-backed pathway from the driver to company economics or a clearly labeled unresolved gap.

---

## 13. Portfolio allocation principles

### 13.1 Concentration is allowed, duplicated hidden bets are not

Position count is not diversification. The Allocator must identify shared exposure to:

- the same macro regime;
- the same rate or FX direction;
- the same geopolitical outcome;
- the same industry capex cycle;
- the same customer/counterparty;
- the same valuation factor;
- the same market-flow regime.

### 13.2 Cost basis is not an investment thesis

For every existing position, the system asks:

> Would a new investor buy this security at the current price with the same capital today?

If not, recovery to the historical purchase price is not by itself a reason to hold.

### 13.3 Sizing remains conservative about false precision

Until forecasts and scenario probabilities are calibrated, the system should not use unconstrained
Kelly sizing or claim optimal mathematical weights.

Sizing support should begin with explicit bands based on:

- edge magnitude;
- thesis confidence;
- payoff asymmetry;
- catalyst proximity;
- liquidity;
- portfolio overlap;
- maximum acceptable thesis-break loss.

Calibration evidence can later justify more formal sizing.

---

## 14. Learning loop and attribution

A realized return alone does not reveal whether the original reasoning was good.

Every resolved thesis should be attributed across at least the following dimensions.

### 14.1 Thesis outcome

- thesis correct;
- thesis partially correct;
- thesis wrong;
- unresolved / catalyst delayed.

### 14.2 Driver attribution

Which component was right or wrong?

- macro;
- industry cycle;
- company transmission;
- earnings forecast;
- expectation gap;
- catalyst timing;
- valuation;
- market flow / positioning;
- entry timing.

### 14.3 Decision attribution

Separate research quality from portfolio implementation:

- security selection;
- entry timing;
- sizing;
- add/trim decisions;
- exit discipline;
- opportunity-cost decision.

### 14.4 Counterfactual attribution

Where data permits, compare the chosen action with the contemporaneous alternatives that were actually
in the opportunity set. Do not compare only against cash or the purchase price.

The purpose of the loop is to learn **which types of calls the system and human PM are actually skilled
at**, and which repeatedly destroy value.

---

## 15. Evaluation framework

### 15.1 Forecast-level metrics

Use target-appropriate predeclared metrics such as MAE, RMSE, directional error, or calibration.
Forecast accuracy is local to the forecast task.

### 15.2 Thesis-level metrics

Primary horizons:

- ~60 trading days;
- ~120 trading days;
- ~250 trading days.

Supporting path horizons can include 1/5/20 days.

Track:

- absolute return;
- benchmark and sector excess return;
- maximum favorable excursion;
- maximum adverse excursion;
- time to thesis catalyst;
- thesis state at the horizon;
- realized catalyst occurrence;
- realized earnings/estimate revision versus thesis.

### 15.3 Ranking-level metrics

The most important system test is cross-sectional:

> Did higher-ranked opportunities subsequently outperform lower-ranked opportunities on the horizon the
> thesis was designed for?

Useful diagnostics include:

- top-bucket minus bottom-bucket return;
- hit rate by rank bucket;
- rank correlation with future returns;
- drawdown by rank bucket;
- sector- and regime-conditioned ranking performance;
- turnover and capital lock-up time.

### 15.4 Portfolio-level metrics

Track long-run capital growth, realized drawdown, opportunity-cost losses, concentration by underlying
risk driver, and benchmark-relative performance as diagnostics.

Do not optimize a backtest metric until the point-in-time data and decision process that generated it
are sufficiently reliable.

---

## 16. Human + machine boundary

Alpha Cycle Lab is intended to be a **Human PM + Machine Research System**.

### Machine responsibilities

- collect and bind evidence;
- enforce point-in-time and revision rules;
- estimate market/industry/company state;
- run frozen forecasts and scenarios;
- compare consensus, internal forecasts, and price-implied assumptions;
- surface opposing evidence and first-rejection risks;
- maintain thesis graphs and catalyst clocks;
- compare opportunity sets;
- preserve decisions before outcomes;
- perform later scoring and attribution.

### Human responsibilities

- decide whether an economically plausible causal claim deserves capital;
- resolve genuinely qualitative ambiguity;
- decide when uncertainty is acceptable rather than merely measurable;
- approve position sizing, concentration, replacement, and exit decisions;
- own final investment action.

The machine should make human reasoning harder to rationalize after the fact, not pretend to eliminate
judgment.

---

## 17. Point-in-time and research-governance invariants

The existing provenance architecture remains mandatory where it prevents false evidence or look-ahead.

Core invariants:

1. no future information in historical decision inputs;
2. preserve source availability time and revision lineage;
3. preserve raw source bytes when economically material and feasible;
4. freeze forecast/evaluation rules before protected outcomes;
5. distinguish facts from inference;
6. do not silently map uncertified provider fields into investment concepts;
7. never rewrite a losing historical thesis into a winning one;
8. successor models use new research-round identities;
9. evidence gaps reduce confidence/readiness rather than being filled with neutral fabricated values;
10. provenance work must be proportional to the economic importance and risk of the decision input.

Rule 10 prevents trust infrastructure from becoming an end in itself.

---

## 18. Development priorities from the current repository state

The current repository already has strong market snapshot, financial/macro snapshot, point-in-time,
revision, backtest, decision-record, execution-playbook, and research-governance foundations.

The highest-value missing layers are therefore not more generic infrastructure.

### Priority 1 — expectation intelligence

Goal: know what must be beaten.

Build only from semantically certified sources:

- consensus estimates;
- estimate count/dispersion where possible;
- estimate revisions;
- guidance versus consensus;
- actual surprise;
- our forecast versus consensus.

The existing KIS raw estimate endpoint remains quarantined until its financial semantics are certified.

### Priority 2 — point-in-time valuation state

Goal: distinguish fundamental strength from priced-in strength.

Required inputs include:

- shares outstanding with effective/availability dates;
- market capitalization;
- net cash/debt and enterprise value where meaningful;
- forward valuation using certified expectations;
- historical regime valuation;
- valuation-sensitive scenario outputs.

### Priority 3 — first sector causal engine: semiconductors

Goal: connect public industry evidence to earnings revisions before the print.

Start narrow and economically explicit rather than broad and feature-heavy.

Candidate families include:

- DRAM/NAND/HBM pricing;
- inventory and utilization;
- capex/capacity and technology migration;
- product mix;
- customer AI capex / demand proxies;
- shipment / ASP / margin transmission.

### Priority 4 — thesis graph + uncertainty schema

Goal: replace a flat composite score as the primary decision object.

Preserve existing scorecards for backward compatibility, but make the thesis graph the forward v2
research unit.

### Priority 5 — opportunity-set comparison

Goal: compare semiconductors with defense, shipbuilding, construction, and other candidates on common
payoff/uncertainty/horizon dimensions without pretending their causal models are identical.

### Priority 6 — learning and attribution

Goal: convert every matured decision into evidence about forecast skill, thesis skill, timing skill,
and allocation skill.

---

## 19. Sequenced implementation plan

### Phase A — architecture freeze

Deliverables:

- this v2 North Star;
- thesis and uncertainty contracts;
- decision/evaluation horizon policy;
- migration map from current scorecards.

No existing prospective experiment is changed.

### Phase B — expectation + valuation foundation

Deliverables:

- certified point-in-time expectation records;
- revision snapshots;
- point-in-time shares / market cap / EV contract;
- valuation state bound to expectation evidence.

Gate:

- no `consensus`, `revision`, or forward-multiple labels without certified semantics.

### Phase C — semiconductor causal graph

Deliverables:

- a minimal driver registry;
- driver → company KPI transmission definitions;
- PIT evidence bindings;
- competing forecast candidates;
- OOD and regime diagnostics.

Gate:

- every driver must have a stated economic pathway and availability policy.

### Phase D — thesis underwriter

Deliverables:

- `InvestmentThesis` snapshot;
- supporting/opposing evidence;
- expectation gap;
- catalyst clock;
- payoff surface;
- uncertainty decomposition;
- kill conditions.

### Phase E — opportunity ranking

Deliverables:

- cross-thesis comparison;
- 3/6/12-month horizon-aware ranking;
- current-position versus replacement comparison;
- portfolio overlap diagnostics.

### Phase F — learning loop

Deliverables:

- matured-thesis labeling;
- driver/forecast/decision attribution;
- rank-performance diagnostics;
- model competence map;
- human-PM competence map where explicitly recorded.

Only after sufficient prospective history should the project consider calibrated probability models or
formal capital-growth optimization.

---

## 20. Stop rules for future development

Do not build a feature merely because it is technically available.

Before implementation, each proposed feature must answer:

1. Which investment uncertainty does this reduce?
2. Which node or edge of the thesis graph does it improve?
3. Can the information be known point-in-time?
4. Does it change a forecast, expectation gap, payoff, catalyst assessment, or allocation decision?
5. What would falsify its claimed usefulness?
6. Is there a higher-value missing input that should be built first?

If a proposed feature cannot answer these questions, it is lower priority.

---

## 21. Definition of success

Alpha Cycle Lab succeeds when, over a growing set of immutable prospective decisions, it can answer:

- Which macro/industry changes did we detect before consensus revision?
- Which transmission models actually predicted company economics?
- Which expectation gaps were real rather than stories?
- Which catalysts closed those gaps and on what timetable?
- Which theses had favorable payoff relative to their uncertainty?
- Did higher-ranked opportunities outperform lower-ranked ones?
- Which positions should have been replaced sooner?
- Which types of analysis consistently add or destroy value?
- Is the combination of machine evidence and human judgment improving long-run capital growth?

That is the standard against which future development should be judged.
