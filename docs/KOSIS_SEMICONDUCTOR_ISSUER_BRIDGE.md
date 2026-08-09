# KOSIS Semiconductor → Issuer Evidence Bridge

This layer connects the verified KOSIS semiconductor-industry history artifact to the
existing Samsung Electronics / SK hynix issuer-observed semiconductor proxy without
changing investment scores.

## Evidence chain

The bridge keeps the evidence chain explicit:

1. KOSIS industry identity
   - `DT_1F02001`, `00/C261`: national semiconductor production / shipment / inventory
   - `DT_1F32001`, `C261`: semiconductor production capacity / utilization
2. KOSIS current-history artifact
   - nine separately bound monthly series
   - raw-index YoY and seasonally adjusted MoM diagnostics
   - revision-sensitive current snapshot
3. Issuer-observed proxy
   - Samsung Electronics (`005930`)
   - SK hynix (`000660`)
   - quarterly revenue, operating income, margin, inventory, capex
   - market-trend confirmation
4. Alignment layer
   - industry direction versus issuer direction
   - descriptive only; no score weight

## Trust boundaries

The current KOSIS history is not a historical vintage archive. Therefore:

- `historical_vintage_certified=false`
- `point_in_time_backtest_eligible=false`
- `heuristic_phase_certified=false`
- `industry_cycle_certified=false`
- `decision_score_enabled=false`

The loader rejects use of a KOSIS artifact when the decision evaluation date precedes
the artifact capture date. It also verifies:

- pointer status and all non-scoring flags;
- nine-series coverage;
- pointer → artifact-directory path binding;
- pointer and manifest artifact IDs;
- recomputed manifest content hash;
- diagnostics content hash from the manifest;
- KOSIS source / organization / source scope;
- latest-period consistency;
- a bounded latest-period lag, currently at most four months.

This prevents the current revised KOSIS snapshot from being silently injected into an
earlier backtest date.

## Company exposure boundary

`C261` is a broad semiconductor-manufacturing industry signal. It does **not** imply
that Samsung Electronics and SK hynix have identical earnings sensitivity to the index.
The bridge deliberately assigns no synthetic company beta or exposure weight.

Company differentiation continues to come from issuer-observed evidence such as:

- revenue YoY;
- operating-income YoY;
- operating-margin change;
- company inventory change;
- capex change;
- market confirmation.

A future company-specific industry sensitivity should require source-backed segment
revenue / profit mapping and product-mix evidence rather than an analyst-invented weight.

## Alignment states

The industry heuristic is reduced only to a descriptive direction:

- recovery / expansion phases → `expansionary`
- contraction / demand-slowdown phases → `contractionary`

The existing issuer proxy is reduced similarly. The bridge then reports one of:

- `industry_issuer_expansion_aligned`
- `industry_issuer_contraction_aligned`
- `industry_issuer_divergent`
- `industry_issuer_alignment_unresolved`

Alignment is evidence for interpretation, not an investment recommendation.

## Decision pipeline behavior

`alpha_cycle.intelligence.build_investment_decision_snapshot` now routes through an
optional final evidence wrapper.

If
`data/private/live-research/kosis-semiconductor-history/latest_kosis_semiconductor_history.json`
exists, it is validated and attached automatically. If it does not exist, the previous
decision behavior is preserved.

When evidence is valid, scorecards and decision records receive industry evidence fields
and the report receives a dedicated KOSIS section. Existing score components and
`composite_score` are not modified.
