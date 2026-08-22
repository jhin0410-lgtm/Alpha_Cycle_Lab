# Semiconductor Causal Engine v1

## Purpose

The semiconductor engine is the first sector-specific causal layer under the common Decision System v2.1 framework.

It does not start by fitting another forecasting model. Its first job is to represent the economic transmission path that a later forecast or Underwriter must justify:

```text
end demand / AI capex
        ↓
AI / HBM demand
        ↓
capacity / technology migration / yield / supply allocation
        ↓
DRAM / NAND / HBM supply-demand
        ↓
price / product mix
        ↓
bit shipment / ASP / company mix
        ↓
revenue / gross margin / operating profit
        ↓
earnings-estimate revisions
        ↓
valuation / positioning
```

A graph edge is not treated as causal merely because two historical series correlate.

## Five critical decision states

Decision System v2.1 caps decision complexity while allowing unlimited evidence complexity. The semiconductor engine therefore freezes five critical states:

1. `ai_hbm_demand`
2. `supply_capacity_yield`
3. `memory_price_mix`
4. `earnings_revision_trajectory`
5. `valuation_positioning`

Each state must map to at least one critical-state node. Additional industry drivers, company drivers, KPIs, accounting metrics, expectation states, valuation states, and catalysts may be represented without an arbitrary node-count cap.

## Source boundary

The engine does not create a new source universe. It binds the existing `config/semiconductor_structural_sources.yaml` as source-policy evidence.

That boundary already distinguishes roles such as:

- Samsung Electronics and SK hynix issuer IR;
- Micron peer IR;
- NVIDIA and AMD customer IR;
- U.S. BIS regulation;
- separately certified/licensed numeric memory-price evidence.

Issuer/customer/peer qualitative pricing commentary cannot silently become numeric memory-price data. Numeric memory price remains subject to its existing semantics, product/unit scope, and reuse-basis requirements.

## Causal nodes

A `CausalNode` identifies a variable in the transmission system. Node types are intentionally economic rather than vendor-specific:

- critical state;
- industry driver;
- company driver;
- company KPI;
- accounting metric;
- expectation state;
- valuation state;
- catalyst.

A node may additionally record a current point-in-time state claim. Observed facts, accounting identities, and empirically validated state claims require evidence. Hypotheses and unvalidated inferences may remain in the graph only while they retain those labels.

## Causal edges

Every `CausalEdge` records:

- source and target nodes;
- economic mechanism;
- epistemic status;
- expected direction;
- transmission lag or explicit condition;
- regime applicability;
- supporting evidence;
- opposing evidence;
- falsifier.

The graph does not suppress contradictory evidence.

### Feedback loops

The engine is deliberately **not forced to be a DAG**. Semiconductor economics can include real feedback mechanisms, for example:

```text
higher prices / margins
    → stronger producer capex incentives
    → later supply growth
    → future pricing pressure
```

Feedback cycles are therefore representable. Direct self-loops are prohibited because they add no useful transmission semantics.

## Epistemic boundary

The graph keeps these capabilities disabled:

- causal proof from correlation alone;
- forecast generation;
- decision scoring;
- investability approval;
- automatic execution.

The graph is evidence architecture for later models and underwriting, not a model itself.

## Point-in-time and revision semantics

Every graph snapshot is content-addressed and append-only. It binds:

- graph policy evidence;
- existing semiconductor source-policy evidence;
- Decision System v2.1 guardrail evidence;
- point-in-time source snapshot references;
- evaluation date and capture timestamp.

A later research state creates a successor graph snapshot linked to the prior snapshot. It does not rewrite the old graph after observing an outcome.

## Relationship to the frozen SK hynix 2026Q3 experiment

The causal engine is a separate next-generation research layer. It does not change the locked 2026Q3 SK hynix company-gross-profit forecast, feature vector, coefficients, persistence benchmark, source capture, or scoring rule.

The frozen experiment can later inform model competence only after its preregistered outcome is observed and scored.

## Next gate

After this foundation is merged, the next high-value step is an **Underwriter integration contract** that requires one investment thesis to explicitly bind:

```text
causal graph
+ forecast registrations
+ certified market expectations
+ forward valuation
+ conditional price-implied requirements
+ counter-thesis / blind-spot package
+ catalysts / payoff scenarios
+ opportunity-set and portfolio-overlap context
```

The Underwriter should return a gated research state, not an automatic trade.
