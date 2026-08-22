# Forward Valuation State — Decision System v2

## Purpose

A strong fundamental outlook is not enough to make a security attractive. The system must ask what
fundamental level is expected and what valuation the current price places on that expectation.

This layer binds two already point-in-time objects:

```text
ValuationEvidenceSnapshot
(PIT shares / security prices / complete market cap)
                    +
ExpectationStateSnapshot
(certified forward level)
                    ↓
ForwardValuationStateSnapshot
```

The output is a transparent forward-multiple state. It is not a fair-value model, target-price model,
or valuation recommendation.

## Enabled multiples

The first version intentionally enables only standard equity multiples with a directly compatible
certified denominator:

- certified forward net income → forward P/E;
- certified forward revenue → forward P/S.

Operating income, gross profit, EBITDA, EPS, and free cash flow observations remain visible as certified
expectation evidence but do not automatically create a multiple in this layer.

EV/EBITDA is deferred until the point-in-time enterprise-value/net-debt bridge is separately certified.
EPS-based P/E is deferred until the price/share-class and diluted-share semantics are explicitly bound.

## No trailing substitution

The existing `valuation.py` layer computes useful trailing valuation evidence from reported annual
financials. Decision System v2 must not relabel those actuals as forward estimates.

If a certified forward net-income or revenue observation is unavailable, this layer does **not** fall
back to trailing actual earnings or revenue. The forward multiple remains unavailable.

## Currency and unit rule

Market capitalization from the existing valuation evidence is denominated in KRW. A certified
expectation must therefore state an explicit supported KRW unit before it can be used:

- `KRW`;
- `KRW_thousand`;
- `KRW_million`;
- `KRW_billion`;
- `KRW_trillion`.

An unknown unit fails closed. The code never guesses whether a provider field is won, thousands,
millions, billions, or hundred-millions of won.

## Market-cap completeness

A forward multiple is available only when the existing valuation evidence marks the issuer's market
capitalization complete across required priced security classes.

A partial market-cap proxy is preserved in the older valuation layer but is not promoted to a forward
multiple denominator here.

## Provider independence

Multiple certified providers may publish a forward value for the same issuer/metric/period. The first
version keeps those observations separate.

It does **not** average providers, choose the most favorable estimate, or synthesize a new consensus.
Any later provider-selection or combination rule must be explicit and point-in-time.

## Snapshot invariants

`ForwardValuationStateSnapshot` binds:

- the exact `ValuationEvidenceSnapshot.snapshot_id`;
- the exact `ExpectationStateSnapshot.snapshot_id`;
- the common evaluation date;
- the later of the two source capture times;
- one transparent valuation observation per certified expectation observation.

Statuses are explicit:

- `available`;
- `market_cap_unavailable`;
- `non_positive_expectation`;
- `unsupported_expectation_metric`.

The content-addressed output also freezes:

- `fair_value_enabled=false`;
- `target_price_enabled=false`;
- `valuation_score_enabled=false`;
- `order_api_enabled=false`.

## Why fair value is deferred

A forward multiple answers:

> What multiple is the current market capitalization paying for this certified expected fundamental?

It does not answer:

> What multiple should the company trade at?

The second question requires additional evidence such as:

- historical forward-multiple distributions constructed with genuine historical expectation vintages;
- peer forward valuations with consistent period and accounting semantics;
- sector/regime context;
- company-specific growth, return, balance-sheet, and duration characteristics.

Until that evidence exists, the system should show the multiple without manufacturing a cheap/expensive
score or target price.

## Next gate

After this foundation is proven, the next high-value work is not another generic valuation formula.
It is the first sector causal engine, starting with semiconductors, plus an expectation-gap object that
can compare a separately frozen internal forecast against a certified market expectation for the same
metric and target period.
