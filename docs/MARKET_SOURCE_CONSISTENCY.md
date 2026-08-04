# Market source consistency gate

Alpha Cycle Lab keeps TossInvest and Kiwoom OpenAPI+ evidence independent. A
provider is never selected because its value looks more favorable, and one source
is never silently substituted for the other.

## Run

After at least one successful Kiwoom market export and one immutable TossInvest
market snapshot exist locally:

```powershell
.\scripts\check_market_source_consistency.cmd
```

This command performs no network calls and does not open a Kiwoom login window.
It reads only local immutable evidence.

## Evidence resolution

The checker resolves TossInvest evidence in this order:

1. `latest_run.json` when it is `completed` and its linked market directory exists.
2. The newest valid immutable directory under `market-intelligence/`.

The second path matters when a later live-pipeline attempt is blocked by a changed
TossInvest IP allowlist and overwrites `latest_run.json`. A blocked status does not
delete the earlier immutable evidence.

Kiwoom evidence is resolved through:

```text
kiwoom-openapi-plus-market/latest_market_export.json
```

The pointer snapshot ID must equal the linked Kiwoom manifest snapshot ID.

## Fail-closed checks

Both sources must provide the exact market universe:

- `005930`: Samsung Electronics common
- `005935`: Samsung Electronics preferred auxiliary valuation evidence
- `000660`: SK hynix

The checker also requires:

- expected provider identity
- daily interval
- unadjusted price basis
- KRW for TossInvest evidence
- disabled account and order capabilities
- unique symbol/date rows
- valid timezone-aware capture timestamps

## Historical daily comparison

Only dates strictly earlier than both provider capture dates in Korea time are
eligible. This excludes an incomplete current-session daily bar.

For each symbol, the newest 20 overlapping completed dates are checked by default.
Open, high, low, and close must match exactly. A completed OHLC disagreement is a
hard failure.

Volume differences are retained in the comparison CSV and surfaced as warnings,
but they do not override matching OHLC evidence. Providers can differ in how they
finalize or expose volume sessions, so volume is not used as the sole source
integrity gate at this stage.

## Live quote comparison

Current quotes are compared only when:

- both snapshots are no more than 30 minutes old; and
- provider capture times are no more than 60 seconds apart.

When those conditions are not met, live quotes are marked `not_comparable`; their
numeric difference is recorded but is not interpreted as a provider conflict.
When comparable, the default tolerance is 50 basis points.

## Status meanings

### `passed`

Historical daily OHLC agrees, live quotes are temporally comparable and within
tolerance, and the evidence is eligible for a later decision-integration gate.
This status still does not automatically inject either source into a decision.

### `passed_historical_only`

Completed daily OHLC agrees, but the two live captures are too old or too far apart
for a valid current-quote comparison. Decision integration remains disabled.

### `failed`

A required source, symbol, basis, timestamp, minimum overlap, or completed daily
OHLC check failed. Decision integration remains disabled.

## Artifacts

Each run writes:

```text
data/private/live-research/
  latest_market_consistency.json
  market-source-consistency/<timestamp>/
    consistency.json
    daily_price_comparisons.csv
    live_quote_comparisons.csv
```

The result records both source snapshot IDs and directories, the historical cutoff,
row-level conflict counts, live comparability, warnings, and failures.

The gate does not enable:

- automatic provider substitution
- account lookup
- holdings or balance collection
- order placement or modification
- automatic trading
