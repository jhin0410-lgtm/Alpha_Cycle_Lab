# Certified Forward Valuation — Decision System v2.1

## Purpose

This layer connects two already-certified point-in-time objects:

```text
PIT market-cap evidence
        +
Certified Expectation State
        ↓
Forward Valuation State
```

It answers only a narrow question:

> What transparent forward market-cap multiple follows from the current certified expectation?

It does **not** decide whether a stock is cheap, calculate fair value, produce a target price, or approve a position.

## v2.1 revalidation

The original forward-valuation implementation was intentionally parked while Decision System v2.1 epistemic guardrails, the generic Forecast Ledger, and independent epistemic-defense contracts were established.

This successor implementation is rebuilt from the current main and binds every `ForwardValuationStateSnapshot` to the active v2.1 guardrail evidence id.

The frozen SK hynix 2026Q3 prospective experiment is not changed or consumed by this layer.

## Enabled metrics

Schema v2 intentionally enables only metrics whose numerator and denominator semantics are transparent with existing evidence:

- certified forward net income + complete PIT market capitalization → `forward_pe`;
- certified forward revenue + complete PIT market capitalization → `forward_ps`.

The following remain disabled:

- EV/EBITDA until a point-in-time enterprise-value/net-debt bridge is certified;
- EPS-based P/E until share-class and diluted-share semantics are explicitly bound;
- fair value;
- target price;
- cheap/expensive scoring;
- automatic execution.

## Fail-closed rules

### No trailing substitution

If a certified forward denominator does not exist, the system does not substitute a reported trailing actual and relabel it as forward.

### No provider averaging

Multiple certified providers remain separate observations. The system does not silently average, select, or weight them.

### Complete market capitalization required

A forward multiple is unavailable when `market_cap_complete` is false. The completeness flag must be an actual boolean; strings such as `"false"` are rejected rather than interpreted through Python truthiness.

### Explicit units only

Only explicitly supported KRW units can be converted:

- `KRW`
- `KRW_thousand`
- `KRW_million`
- `KRW_billion`
- `KRW_trillion`

Unknown scaling is rejected rather than guessed.

### Non-positive denominator

A non-positive forward earnings denominator cannot create a positive P/E. The certified expectation remains visible, but the forward multiple is marked unavailable.

## Snapshot provenance

Each immutable forward-valuation snapshot binds:

- valuation evidence snapshot id;
- expectation state snapshot id;
- Decision System v2.1 guardrail evidence id;
- evaluation date;
- capture timestamp;
- provider-specific expectation identity;
- source evidence for each expectation observation.

Persistence exposes a mutable latest pointer only to locate the immutable content-addressed snapshot.

## Next gate

The next layer is **Price-Implied Expectation**, not target-price generation.

It should ask what operating assumption would be required to justify the observed market value under an explicitly frozen valuation frame. That price-implied view must remain separate from:

```text
OUR VIEW
MARKET / CONSENSUS VIEW
PRICE-IMPLIED VIEW
```

Only after those views are represented separately should the semiconductor causal engine and later Underwriter compare the variant wedge.
