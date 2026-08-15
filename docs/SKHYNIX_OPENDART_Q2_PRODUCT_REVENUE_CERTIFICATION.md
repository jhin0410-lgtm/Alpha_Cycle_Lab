# SK hynix 2Q26 OpenDART direct product-revenue certification

## Purpose

The official 2Q26 SK hynix IR chart certifies that the displayed `73%` token belongs to DRAM and `27%` belongs to NAND, while a positive-area `Others` segment remains numerically unlabeled. The IR chart is therefore an independent presentation/comparability check, not a source for `Other=0` or residual allocation.

This stage discovers the official OpenDART `반기보고서 (2026.06)` and certifies current-quarter DRAM, NAND, Other, and Total revenue directly from the periodic filing.

## Actual 2026 filing layout

Preserved receipt `20260814003509` proves that the consolidated product header and the revenue row are emitted as adjacent tables. Under `21. 매출액 (연결)`, the product header contains:

`DRAM | NAND Flash | 기타 | 부문 합계`

Each group has `3개월` and `누적` subcolumns. The immediately following data table contains a plain `수익` row with eight corresponding amounts. The production parser binds those adjacent tables, selects the current-period `3개월` cells, and separately excludes the standalone `20. 매출액` table.

## Observed 2Q26 direct source facts

The consolidated filing reports the following current-quarter values in KRW million:

| product | 2Q26 revenue |
|---|---:|
| DRAM | 56,982,743 |
| NAND Flash | 21,959,898 |
| Other | 376,105 |
| Total | 79,318,746 |

The source reconciles exactly:

`56,982,743 + 21,959,898 + 376,105 = 79,318,746`.

These values are direct source facts. They are not produced by a share-allocation resolver.

## Source boundary

The collector and verifier:

1. resolve SK hynix through the OpenDART corporation registry;
2. require the exact `반기보고서 (2026.06)` filing in the configured window;
3. archive the exact `/api/document.xml` ZIP bytes and SHA-256;
4. archive normalized text and its SHA-256;
5. bind the exact parser/source contract into a chain evidence ID;
6. replay the archived ZIP instead of trusting a previously parsed JSON value;
7. refuse truncated normalized text;
8. require a supported KRW unit;
9. require the consolidated `매출액 (연결)` scope;
10. require a unique current-period DRAM/NAND/Other/Total `3개월` mapping;
11. accept the live `수익` row and retained compatibility aliases;
12. reconstruct raw HTML/XML table geometry, including split adjacent header/data tables;
13. require normalized-text and structured-source parses to reproduce the same metrics; and
14. require direct product amounts to reconcile to the reported total.

No `Other=100-DRAM-NAND`, chart-height allocation, or hidden residual is permitted.

## Failure diagnostics

A failed live parse preserves the source under:

`data/private/research/skhynix-opendart-q2-product-revenue-certification/failed/`

The bundle contains the exact ZIP, normalized text, and diagnostic metadata. The offline diagnostic command verifies hashes and inventories relevant text/table grids without making another OpenDART request.

## Bound replay

The verifier reconstructs `PeriodicProductRevenueSpec` from archived `parser_contract.json`, not from a later registry state. Contract, ZIP, or normalized-text tampering breaks verification. A standalone `certification.json` is not a production promotion boundary; consumers enter through the bound pointer and verifier.

## Independent official-IR comparison

The OpenDART amounts are converted to percentages only for an independent comparison with the IR chart. For the observed direct values, the derived shares are approximately:

- DRAM: `71.8402%`
- NAND: `27.6856%`
- Other: `0.4742%`

Those figures do not reproduce the IR chart's `73% / 27%` labels under ordinary integer rounding. The comparison is therefore classified as:

`official_source_share_identity_mismatch`

This status means the two official presentations are not certified as directly share-comparable under the current evidence. It does **not** mean that the directly reported OpenDART amounts are invalid.

The IR comparison remains visible through separate fields:

- `semiconductor_direct_product_revenue_ir_crosscheck_certified`
- `semiconductor_direct_product_revenue_ir_share_identity_match`
- `semiconductor_direct_product_revenue_ir_comparison_status`

## Revenue input readiness versus comparability

A bound, replayable, reconciled OpenDART direct-product certification is sufficient to make the **revenue-only** model input available:

`semiconductor_direct_product_revenue_model_input_ready=true`

This readiness no longer depends on the unrelated IR share identity matching. The IR chart remains an independent diagnostic rather than a veto over direct accounting source facts.

This does **not** certify a complete operating model. Product-specific gross profit or gross margin remains unproven.

## Decision-chain integration

The calibrated chain routes:

`accounting identity -> direct product revenue -> derived allocation -> company actual -> ...`

The direct-product layer remains non-scoring. A source/comparability conflict is recorded as evidence metadata rather than converted into a zero score or used to overwrite source values.

## Gates that remain closed

Even when the direct revenue block is model-input-ready:

- `allocation_resolver_registered=false` — direct amounts do not require allocation;
- `product_profitability_certified=false`;
- `full_baseline_certified=false`;
- `numeric_forecast_enabled=false`;
- `fair_value_estimate_enabled=false`;
- `target_price_enabled=false`; and
- `decision_score_enabled=false`.

The forward-model contract still requires product profitability inputs. Consolidated gross profit or gross margin cannot be silently allocated between DRAM and NAND.

## Windows execution

```powershell
cd "C:\Download\쿠쿠\coding\Alpha_Cycle_Lab"
git pull --ff-only
.\scripts\report_skhynix_opendart_q2_product_revenue_certification.ps1
```

The launcher reads `OPENDART_API_KEY` only for live OpenDART access and never writes the key to logs/artifacts. Successful private artifacts include the original ZIP, normalized text, certification, bound parser contract, certification pointer, and product-revenue readiness report.
