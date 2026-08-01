# Valuation and Financial History Intelligence

This layer converts official OpenDART share counts, multi-period financial statements, and an immutable TossInvest market snapshot into point-in-time valuation evidence.

## Why this is a separate snapshot

The research snapshot preserves filing, macro, and disclosure facts. The valuation snapshot adds two assumptions that must remain explicit:

1. which listed symbol prices each OpenDART equity class; and
2. which market snapshot supplies the reference price.

The layer therefore does not silently multiply a common-share price by total shares when preferred or other equity classes exist.

## Official read-only inputs

- `/api/stockTotqySttus.json`
  - issued shares
  - treasury shares
  - floating shares
  - security type and settlement date
- `/api/fnlttSinglAcntAll.json`
  - current quarter amount for interim income statements
  - cumulative current amount
  - prior-year same-quarter and cumulative amounts
  - annual and balance-sheet facts
- immutable market snapshot
  - symbol
  - price
  - price timestamp

Only the official OpenDART host is allowed. Account and order routes remain unavailable.

## Security-class mapping

OpenDART identifies share classes by the `se` text. Market data identifies securities by symbol. An exact mapping is required when a company has preferred or other priced equity classes.

```yaml
companies:
  "005930":
    securities:
      "보통주": "005930"
      "우선주": "005935"
```

A single common-share row defaults to the company's six-digit ticker. Preferred and other classes do not receive inferred symbols.

If any issued equity class lacks a mapping or price:

- `market_cap_complete` is false;
- `market_cap_proxy` preserves only the priced portion;
- PER, PBR, PSR, earnings yield, and FCF yield remain unavailable;
- valuation does not enter the decision score.

## Build a valuation snapshot

```powershell
python -m alpha_cycle.valuation_cli `
  --research-snapshot $research.FullName `
  --market-snapshot $market.FullName `
  --history-years 3 `
  --fs-div CFS `
  --security-config config/security_mappings.local.yaml `
  --output data/private/valuation-intelligence
```

Outputs:

- `shares.csv`
- `security_values.csv`
- `financial_history.csv`
- `valuation_metrics.csv`
- `raw_valuation.json`
- `manifest.json`

## Financial-history semantics

For Q1, half-year, and Q3 income statements, OpenDART's current amount is treated as the current three-month amount and its add amount is treated as year-to-date. The labels are normalized to Q1, Q2, and Q3.

Q4 is derived only when the same company and fiscal year contain both:

- a visible annual report; and
- a visible Q3 report.

The calculation is:

```text
Q4 = FY annual amount - Q3 cumulative amount
```

The same subtraction is applied to prior-year comparison fields when both values are available. Derived rows are marked `derived=true`.

The history table calculates:

- revenue growth
- operating-income growth
- net-income growth
- operating margin
- year-over-year margin change
- free cash flow on the available cumulative basis
- sequential change in year-over-year growth for quarterly rows

Missing accounts remain missing. They are not filled with zero.

## Valuation metrics

When company market capitalization is complete and a visible annual financial reference exists, the layer calculates:

- market capitalization
- PER
- PBR
- PSR
- earnings yield
- FCF yield

Negative or zero denominators do not produce misleading multiples.

## Valuation score

The valuation score is not a fair-value estimate. It is calculated only when at least two companies have complete valuation evidence.

For each eligible company:

- lower PER, PBR, and PSR rank higher;
- higher FCF yield ranks higher;
- available percentile ranks are averaged;
- the result is mapped to 1–5;
- small peer sets are shrunk toward the neutral score of 3.

This means the score is relative to the snapshot universe and must not be read as an absolute cheap/expensive conclusion.

## Connect valuation to the decision report

```powershell
python -m alpha_cycle.decision_cli build `
  --research-snapshot $research.FullName `
  --market-snapshot $market.FullName `
  --valuation-snapshot $valuation.FullName `
  --company-config config/company_exposures.local.yaml `
  --output data/private/decision-intelligence
```

The decision snapshot validates that research, market, valuation, and evaluation-date identifiers all match. A valuation snapshot linked to another price or research basis is rejected.

## Boundaries

- This layer uses reported annual results, not analyst consensus or forward estimates.
- Market capitalization is complete only when every issued priced equity class is mapped.
- It does not infer preferred-share symbols.
- It does not calculate enterprise value because authoritative interest-bearing debt and all priced equity classes are not yet guaranteed.
- It does not infer dilution from options, convertible securities, or unexercised rights.
- OpenDART live endpoints cannot reconstruct every superseded historical filing vintage.
- Relative valuation ranks are not target prices, expected returns, or probabilities.
