# SK hynix third-wave product structure diagnostic

## Why this exists

The 2017Q1-2018Q3 third-wave acquisition closes all six issuer-driver layers and all six
consolidated company-profitability layers, but the preserved product-revenue recovery can
still return `accepted=0`. That failure is not evidence that product revenue is absent. It
only says the existing 2019-2020 recovery contract did not find exactly one table satisfying
its registered structure.

The next scientifically valid step is to diagnose the preserved source geometry before
changing the recovery contract.

## What is reported

For every failed 2017-2018 product period, the identification CLI inspects the latest
hash-verified preserved OpenDART ZIP and reports product-token tables with:

- structured and malformed table counts;
- exact DRAM, NAND, Other, and Total label columns;
- whether all four labels share one column;
- current-period and `3개월` header columns;
- presence of `백만원` and revenue context;
- bounded samples of first-column and first-nonempty labels;
- explicit structural reasons why the current recovery shape does not match.

The report is written only under the existing private research output. Raw filing bytes are
not committed to the public repository.

## Trust boundary

This stage is diagnostic only.

- No source row is certified or promoted by the diagnostic.
- `Other = Total - DRAM - NAND` is **not** an allowed derivation.
- No product split is guessed.
- No v1 or v2 model is fit or refit.
- The spent 2026Q1 observation is not reclassified as unseen.
- The reserved 2026Q3 holdout is neither loaded nor evaluated.
- Forecast, valuation, target-price, and decision outputs remain disabled.

A new recovery rule may be registered only after the six real filings show a common,
source-supported structure. The rule must then retain direct reported product amounts and an
independent consolidated-revenue reconciliation before any row can become source-complete.
