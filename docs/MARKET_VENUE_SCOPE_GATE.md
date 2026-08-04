# Market venue-scope gate

The TossInvest/Kiwoom comparison must establish that two daily series cover the
same market and session scope before treating every OHLC difference as provider
corruption.

## Observed evidence pattern

The August 4, 2026 local comparison produced this strict pattern across the newest
20 completed dates:

- `000660`: all 20 OHLC rows and all 20 volume rows differed.
- `005930`: all 20 OHLC rows and all 20 volume rows differed.
- `005935`: all 20 OHLCV rows matched exactly.

The first two securities are venue-variable evidence in the narrow policy used by
this three-symbol audit universe. The preferred-share security is the control.
The pattern is inconsistent with a random parsing error, universal date offset,
or universal adjusted-price error because the control series agrees exactly.

## Provider contracts

The stored TossInvest candle evidence has no venue selector or explicit historical
market-scope field. It is therefore labelled:

```text
provider_unspecified_domestic_scope
```

The stored Kiwoom evidence was requested through `opt10081`, with no venue input
in the exporter, and is labelled:

```text
krx_opt10081
```

These labels describe the stored request contracts. They do not assert that one
provider is correct and the other is wrong.

## Classification

A legacy comparison is classified as `inferred_venue_scope_mismatch` only when all
of the following are true:

1. Both venue-variable securities have the required number of rows.
2. Every price row and every volume row differs for both securities.
3. Every OHLCV row matches for the control security.
4. The Kiwoom manifest records `opt10081` and unadjusted prices.
5. The Toss manifest records an unadjusted daily series.
6. The manifests do not explicitly declare the same historical market scope.

The result status becomes:

```text
blocked_market_scope_mismatch
```

The raw 40 OHLC differences remain immutable evidence, but they are separated
into:

- `raw_price_difference_count = 40`
- `scope_incompatible_row_count = 40`
- `comparable_scope_price_conflict_count = 0`

This is an inference about comparability, not proof of the exact venue composition
inside the Toss series.

## Fail-closed behavior

A scope mismatch does not pass the gate:

- decision integration remains disabled;
- automatic provider substitution remains disabled;
- account and order APIs remain disabled;
- the price tolerance remains zero won;
- neither source replaces the other;
- no historical data is rewritten.

A sporadic mismatch, a control-symbol mismatch, or a mismatch under explicitly
equal market scopes remains a true or unresolved price conflict.

## Artifacts

The original raw result remains under:

```text
data/private/live-research/market-source-consistency/<timestamp>/consistency.json
```

The scope assessment is written beside it:

```text
data/private/live-research/market-source-consistency/<timestamp>/market_scope_assessment.json
```

The latest assessment pointer is:

```text
data/private/live-research/latest_market_scope_assessment.json
```

The assessment references the raw result ID and path, so both layers remain
replayable and auditable.

## Primary-source references

- Toss Securities Open API canonical specification: the candle endpoint exposes
  symbol, interval, count, cursor, and adjusted-price inputs, but no venue input.
- Nextrade official market information: Samsung Electronics and SK hynix are
  traded through the alternative venue and Nextrade operates pre-market and
  after-market sessions.
- Kiwoom OpenAPI+ and HTS help: integrated KRX/NXT views exist in Kiwoom products,
  but the current exporter uses legacy `opt10081` without an integrated-market
  selector.

The official sources establish that venue/session scope can differ. They do not
establish the exact composition of every legacy candle returned by either provider,
which is why the result remains blocked rather than automatically reconciled.
