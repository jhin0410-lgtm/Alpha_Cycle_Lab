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

`hbm_mix_overlay` remains non-additive so HBM is not double counted as separate company
revenue. `corporate_other` remains a company-level operating/net-income bridge rather than
a product-revenue substitute.

Even when all derived revenue blocks reconcile, the derived allocation layer does not
change the direct baseline certification or unlock Expectation Gap, numeric forecasts,
valuation targets, scenario probabilities, or decision scoring.

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
