# Investment Decision Intelligence

This layer converts immutable market and research snapshots into an explainable,
non-executing investment decision package.

## What it does

1. Reads the linked TossInvest market snapshot and OpenDART/ECOS research snapshot.
2. Extracts canonical current/prior financial KPIs from the preserved raw OpenDART rows.
3. Calculates growth, margins, ROE, leverage, cash conversion, and free cash flow.
4. Classifies disclosure titles into material catalysts, monitoring events, and noise.
5. Summarizes rate, FX, and generic macro series into descriptive regimes.
6. Calculates 1/5/20/60-period returns, volatility, drawdown, moving-average distance,
   volume change, and relative-strength ranks.
7. Produces component scores, opposing evidence, invalidation conditions, and a Korean
   Markdown report.
8. Stores decision records that can later be labeled with realized 1/5/20/60-trading-day
   returns, maximum upside, maximum drawdown, and optional benchmark excess return.

## Important boundaries

- Scores are transparent heuristics, not probability estimates.
- Valuation and sell-side consensus are deliberately marked unavailable until a
  point-in-time shares, market-cap, estimate, and revision data layer exists.
- Missing components reduce score coverage instead of being silently replaced with a
  neutral score.
- Company FX and rate sensitivities are explicit YAML assumptions, never hidden in code.
- Disclosure classification uses filing-title rules. It does not read the full filing body.
- Macro regimes describe observed direction. They do not claim structural causality.
- No order, account, or position API is enabled.

## Build a decision snapshot

```powershell
$research = Get-ChildItem data/private/research-intelligence -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

$market = Get-ChildItem data/private/market-intelligence -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

Copy-Item `
  config/company_exposures.example.yaml `
  config/company_exposures.local.yaml

python -m alpha_cycle.decision_cli build `
  --research-snapshot $research.FullName `
  --market-snapshot $market.FullName `
  --company-config config/company_exposures.local.yaml `
  --output data/private/decision-intelligence
```

The source snapshot IDs must match. A research snapshot cannot be combined with an
unrelated market snapshot.

## Output files

- `financial_kpis.csv`: canonical KPIs and derived ratios by ticker.
- `financial_kpi_mapping.csv`: exact OpenDART account selected for every canonical KPI.
- `disclosure_events.csv`: every filing with category, priority, materiality, and noise flag.
- `catalysts.csv`: recent high/critical non-noise filings.
- `disclosure_summary.csv`: per-company disclosure counts.
- `macro_regime.csv`: latest values, changes, and descriptive regime labels.
- `market_context.csv`: return, volatility, drawdown, trend, and relative-strength context.
- `scorecards.csv`: component scores, data coverage, evidence, and invalidation triggers.
- `decision_records.csv`: reference prices and decision states for future labeling.
- `report.md`: Korean decision-support report.
- `manifest.json`: content hash, source snapshot IDs, limitations, and safety boundaries.

## Score coverage

The composite uses available components and reports the fraction of total intended weight
that was actually observed. The intended weights are:

- earnings momentum: 25%
- financial quality: 20%
- catalysts: 15%
- market timing: 15%
- macro fit: 10%
- valuation: 15%

Valuation is currently unavailable. Without a company-exposure YAML, macro fit is also
unavailable. These gaps reduce coverage and are preserved in the report.

## Outcome labels

After a later market snapshot contains enough sessions beyond the decision date:

```powershell
$decision = Get-ChildItem data/private/decision-intelligence -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

$futureMarket = Get-ChildItem data/private/market-intelligence -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

python -m alpha_cycle.decision_cli label `
  --decision-snapshot $decision.FullName `
  --future-market-snapshot $futureMarket.FullName `
  --horizons 1,5,20,60 `
  --output data/private/outcome-labels
```

Unresolved horizons remain explicit null labels. The system never invents a future return.

## Next authoritative data layers

The following remain necessary for a full investment process:

1. point-in-time share count, market capitalization, and enterprise value;
2. consensus estimates and estimate-revision history;
3. segment, product, capacity, order backlog, and industry supply-demand data;
4. benchmark and sector-index market snapshots;
5. archived full-filing text and structured filing-body event extraction;
6. walk-forward evaluation, calibration, and champion/challenger model governance.
