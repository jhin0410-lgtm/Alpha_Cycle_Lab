# Read-only market intelligence

## Scope

`market-intel` collects current prices and candle history from the official Toss Securities
Open API, calculates explainable technical features, and stores one immutable local snapshot.
It does not query accounts and has no order create, modify, cancel, or conditional-order path.

The first implementation is a one-shot collector. Continuous scheduling, DART financials,
ECOS macro series, industry competition evidence, catalyst tracking, outcome labels, and model
promotion are separate roadmap stages.

## Credentials

Set secrets only in the local process environment or an ignored `.env` workflow:

```text
TOSSINVEST_CLIENT_ID=...
TOSSINVEST_CLIENT_SECRET=...
```

Never commit real values. The adapter allows only `https://openapi.tossinvest.com`, and error
messages never include the access token or client secret. Market-data calls require no account
header.

## CLI

```bash
python -m alpha_cycle.cli market-intel --symbols 005930,000660 --interval 1d --count 100 --no-adjusted --output data/private/market-intelligence
```

Supported candle intervals are `1m` and `1d`. The official API returns at most 200 candles, so
`count` must be between 1 and 200. Current-price requests support at most 200 unique symbols.

The project default is `--no-adjusted`. This prevents the provider's adjusted-price default from
being used silently. Use `--adjusted` only when the analysis explicitly requires adjusted candle
history. Snapshot metadata and every candle preserve the selected basis.

## Features

The feature table records:

- 1, 5, and 20-period simple returns
- 5 and 20-period simple moving averages
- price distance from the 20-period average
- 20-period annualized realized volatility
- current volume relative to the prior 20-period average
- drawdown from the trailing 20-period high
- 14-period RSI
- 20-period trend efficiency and direction
- cross-sectional percentile rank of 20-period return

Insufficient history produces an empty value rather than an estimate. These features describe
price and liquidity behavior; they do not prove future direction or replace fundamental,
industry, macro, valuation, or catalyst analysis.

## Snapshot contract

Each collection writes a content-addressed directory:

```text
<UTC timestamp>__<first 12 characters of SHA-256>/
  manifest.json
  prices.csv
  candles.csv
  technical_features.csv
  raw_prices.json
  raw_candles.json
```

The snapshot ID is the SHA-256 digest of canonical normalized content, including the raw response
payloads and capture time. Rewriting the same snapshot is idempotent. Conflicting existing output
fails closed. Access tokens and credentials are never part of the snapshot.

The raw payloads are retained locally so a future parser change can be audited against the exact
provider response. `data/private/` and output directories remain ignored by Git.

## Runtime behavior

The API currently provides REST rather than WebSocket streaming. A future scheduler may run this
one-shot command at an explicit interval while respecting response rate-limit headers. The client
already:

- caches access tokens until shortly before expiry
- retries HTTP 429 and transient 5xx responses
- honors `Retry-After` when present
- refreshes a token once after HTTP 401
- validates response schemas, timestamps, currencies, OHLC consistency, and duplicates
- structurally rejects any path outside the read-only market-data allow-list

Passing this collection step does not authorize account access or order submission.
