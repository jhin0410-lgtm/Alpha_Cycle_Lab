# Conditional Price-Implied Requirements — Decision System v2.1

## Purpose

A market price does not reveal one uniquely identifiable market forecast. The same market capitalization can be rationalized by different combinations of earnings, revenue, growth, risk, and valuation multiples.

Decision System v2.1 therefore does **not** label reverse valuation as a certified market expectation.

Instead it records a conditional question:

> Given the observed point-in-time market capitalization and a separately frozen reference multiple, what operating result would be required to support that valuation frame?

The three views remain distinct:

```text
OUR FUNDAMENTAL VIEW
        !=
CERTIFIED MARKET / CONSENSUS EXPECTATION
        !=
CONDITIONAL PRICE-IMPLIED REQUIREMENT
```

## Reference frames

A `ValuationReferencePoint` may come from:

- a historical forward-valuation vintage;
- peer forward comparable evidence;
- an explicitly labelled scenario assumption.

Historical or peer evidence requires source evidence references. A scenario assumption may be used without external evidence only because it is explicitly labelled as an assumption, never as observed market belief.

No reference point is automatically selected as the correct multiple. Multiple reference points form a **surface**.

## Reverse calculations

Current schema v1 supports only the transparent market-cap frames already enabled by certified forward valuation:

```text
market cap / forward P/E reference multiple
    -> required forward net income

market cap / forward P/S reference multiple
    -> required forward revenue
```

Example:

```text
PIT market cap = KRW 100bn
reference P/E = 10x
conditional required net income = KRW 10bn
```

This means only:

> KRW 10bn of net income is required for KRW 100bn market capitalization to equal 10x forward P/E.

It does **not** mean the market consensus is KRW 10bn.

## Fail-closed rules

- complete point-in-time market capitalization is required;
- `market_cap_complete` must be an actual boolean;
- reference multiples must be finite and positive;
- evidence-based reference frames require evidence ids;
- reference observations cannot occur after the evaluation date;
- target periods must remain forward at the evaluation date;
- valuation evidence and reference frame must share the same evaluation date;
- all snapshots bind to the active Decision System v2.1 guardrail evidence id.

## Explicit non-capabilities

This layer does not:

- certify market consensus;
- infer one true price-implied forecast;
- choose the correct valuation multiple;
- estimate fair value;
- issue a target price;
- create a decision score;
- approve a position;
- execute an order.

## Investment use later

Once a sector/company causal engine can produce an internal operating forecast and a certified expectation source is available, the Underwriter can compare:

```text
Our forecast
vs certified market expectation
vs the operating requirement under several price/multiple frames
```

That comparison can reveal whether an apparent fundamental edge is already embedded in the current valuation, but it must preserve the uncertainty created by the reference-multiple assumption.

## Next gate

The next implementation target is the **Semiconductor Causal Engine**. It should represent the economic transmission path from industry state changes to company earnings and estimate revisions before the system attempts an end-to-end Underwriter.
