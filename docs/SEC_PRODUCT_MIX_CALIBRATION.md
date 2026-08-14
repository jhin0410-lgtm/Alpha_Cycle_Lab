# SK hynix SEC Product-Mix Calibration

This research artifact calibrates a **method**, not a current-quarter forecast or baseline.

## Official source

The checked-in registry pins the final SK hynix SEC `424B4` prospectus filed on
2026-07-10:

- accession: `0001193125-26-299963`
- primary document: `d32785d424b4.htm`
- accounting period: 2026-01-01 through 2026-03-31

The filing directly reports first-quarter 2026 product revenue in KRW billions:

| Product category | Revenue |
|---|---:|
| DRAM | 40,659 |
| NAND flash | 11,574 |
| Other products | 343 |
| Total revenue | 52,576 |

It separately reports DRAM and NAND revenue shares of 77.3% and 22.0%.

`Other products` is therefore a real disclosed revenue category. Alpha Cycle must not
construct it as a residual such as `100% - DRAM share - NAND share` and then relabel that
residual as a source fact.

## What the calibration proves

The one-decimal reported DRAM/NAND shares can be applied to the directly reported company
revenue and compared against the directly reported DRAM/NAND product revenue. The
historical calibration allows the direct-share method only when its reproduction error is
within the checked-in tolerance.

The calibration evidence ID is separate from current-quarter input evidence IDs. A future
current-quarter allocation resolver must verify both:

1. current-quarter source inputs, and
2. a distinct historical method-calibration artifact.

Current source verification does not automatically certify the allocation method.

## Rounded-share reconciliation

Issuer product shares are reported to one decimal place, so applying those shares to a
company-revenue amount is not expected to reproduce directly reported product amounts to
machine precision. The official 1Q26 shape demonstrates this explicitly:

- company revenue: 52,576
- DRAM share-derived revenue: 40,641.248
- NAND share-derived revenue: 11,566.720
- directly reported Other-products revenue: 343
- combined model revenue: 52,550.968
- reconciliation delta: -25.032

Alpha Cycle therefore permits a source resolver to request a reconciliation tolerance of
at most **0.1% of reported company revenue**. This is a hard v1 ceiling derived from the
historical method-calibration boundary, not a generic balancing plug.

A positive tolerance is permitted only when an explicit source-bounded
`other_products_services_revenue` amount is present. The tolerance cannot:

- substitute for a missing revenue block,
- create `Other` as a residual,
- absorb a large product-definition mismatch,
- certify profitability or the full company baseline.

DRAM and NAND share inputs are also pinned to their registered block semantics. A share
with another semantic ID cannot be substituted into either block.

## What the calibration does not prove

The 1Q26 product mix is not a 2Q26 product baseline. The artifact therefore keeps all of
the following disabled:

- `current_baseline_eligible`
- `q2_allocation_eligible`
- `historical_vintage_certified`
- `point_in_time_backtest_eligible`
- `numeric_forecast_enabled`
- `decision_score_enabled`

The production `ALLOCATION_SOURCE_RESOLVERS` registry remains intentionally empty until a
same-period current-quarter source resolver independently verifies all required revenue
blocks.

## SK hynix revenue reconciliation contract

SK hynix company revenue now requires three explicit additive revenue blocks:

1. `dram_total`
2. `nand_and_solutions`
3. `other_products_services`

`other_products_services` may enter the allocation artifact only through an explicitly
verified direct amount. The wrapper remains marked as derived/non-source-fact while
retaining the underlying source input and source evidence IDs; no residual arithmetic is
used.

`hbm_mix_overlay` remains non-additive so HBM is not double counted as separate company
revenue. `corporate_other` remains a company-level operating/net-income bridge rather than
a product-revenue substitute.

Even when all revenue blocks reconcile, the derived allocation layer does not change the
direct baseline certification or unlock Expectation Gap, numeric forecasts, valuation
targets, scenario probabilities, or decision scoring.

## One-shot Windows capture

Set an SEC EDGAR User-Agent locally using an application identifier and a reachable
contact email, for example:

```powershell
$env:SEC_EDGAR_USER_AGENT = "AlphaCycleLab your-email@example.com"
```

Then capture the official historical calibration bytes once:

```powershell
.\scripts\capture_sec_product_mix_calibration.ps1
```

The command archives the SEC submissions JSON, the filing HTML bytes, parsed calibration
payload, manifest, and latest pointer under `data/private/research/sec-product-mix-calibration`.
The loader re-parses archived source bytes before accepting persisted calibration values.
