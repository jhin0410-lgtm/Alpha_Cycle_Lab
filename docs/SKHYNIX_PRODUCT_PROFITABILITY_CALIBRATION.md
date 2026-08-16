# SK hynix product-profitability calibration boundary

## Why this stage exists

SK hynix 2Q26 direct product revenue is now source-certified from OpenDART. The forward operating model, however, requires a profitability output for the additive DRAM and NAND blocks. Revenue and profitability are different dimensions.

For DRAM and NAND, a company-level profit total alone does not uniquely identify both product margins. Even in the simplified two-product case,

`company gross profit = DRAM revenue × DRAM margin + NAND revenue × NAND margin + other effects`

contains more unknown product economics than independent product-level profit observations. Adding an Other block, operating expenses, corporate items, or product-mix overlays increases rather than removes the identification problem.

## Direct-source route

Product profitability can be certified as a source fact only when the required product blocks have directly disclosed numeric profitability evidence with a certified period, scope, unit, and source provenance.

For the current SK hynix forward contract, the required profitability blocks are:

- `dram_total` -> `gross_profit_or_margin`
- `nand_and_solutions` -> `gross_profit_or_margin`

The `other_products_services` block currently requires revenue but not a product-profitability output.

## What is forbidden as a source fact

The following shortcuts must remain false at the source-fact boundary:

- allocate company gross profit to DRAM/NAND in proportion to revenue;
- solve a missing product margin as an unexplained residual;
- copy a peer's DRAM/NAND margin into SK hynix;
- convert qualitative issuer commentary into an undisclosed numeric margin;
- treat HBM or eSSD mix commentary as a directly reported product-margin scalar.

Those may become inputs to an explicitly labeled calibration methodology only after the method is specified, historically tested, and frozen. They cannot be renamed as issuer-reported facts.

## Current state

The machine-readable identifiability gate reports the current product-profitability coverage separately from direct revenue readiness. With direct DRAM/NAND revenue available but no certified direct product-margin metrics, the intended status is:

- `identifiable_from_source_facts=false`
- `direct_product_profitability_metrics_required=2`
- `direct_product_profitability_metrics_available=0`
- `calibrated_assumption_required=true`
- `calibration_status=direct_product_profitability_source_facts_missing`
- `product_profitability_certified=false`
- `numeric_forecast_enabled=false`
- `decision_score_enabled=false`

## Calibration route

A future calibrated product-profitability method should remain inside the existing semiconductor operating-assumption framework and should not mutate the direct-source baseline. At minimum, the method should define:

1. exact target variable — DRAM/NAND gross margin, gross profit, or another explicitly reconciled profitability measure;
2. historical observation set and point-in-time vintage rules;
3. first-party supporting evidence for company profitability and product revenue;
4. explicit cycle drivers such as ASP, bit shipment, product mix, HBM/eSSD mix, utilization, process-cost improvement, and FX where supported;
5. treatment of Other/corporate economics and reconciliation to company totals;
6. parameter estimation or scenario-construction method;
7. out-of-sample or rolling historical calibration criteria;
8. acceptable error bands and invalidation criteria;
9. frozen method/version and reproducible evidence IDs; and
10. a clear distinction between source facts, calibrated assumptions, and forward scenario outputs.

Until those conditions are implemented and verified, product profitability remains a known missing model dimension rather than an estimated fact.
