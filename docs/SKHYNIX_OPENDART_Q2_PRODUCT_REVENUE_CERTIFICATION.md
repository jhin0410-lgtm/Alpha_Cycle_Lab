# SK hynix 2Q26 OpenDART direct product-revenue certification

## Purpose

The official 2Q26 SK hynix IR chart certifies that the displayed `73%` token belongs to DRAM and `27%` belongs to NAND, while a positive-area `Others` segment remains numerically unlabeled. The IR chart is therefore an independent semantic cross-check, not a source for `Other=0` or residual allocation.

This stage discovers the official OpenDART `반기보고서 (2026.06)` and certifies current-quarter DRAM, NAND, Other, and Total revenue directly from the periodic filing.

## Actual 2026 filing layout

The preserved live receipt `20260814003509` proved two assumptions in the first production parser were wrong:

1. the product header grid and the revenue data row are emitted as adjacent HTML/XML tables rather than one table; and
2. the live data-row label is plain `수익`, not `수익(매출액)`.

Under the consolidated `21. 매출액 (연결)` note, the product header is:

`DRAM | NAND Flash | 기타 | 부문 합계`

Each product group contains `3개월` and `누적` subcolumns. The immediately following data table contains one `수익` row with the eight corresponding amounts. The production parser therefore binds the current-period consolidated header table to its adjacent data table and reads the four `3개월` cells.

The filing also contains a standalone `20. 매출액` product table. The production path requires the consolidated `매출액 (연결)` heading and rejects the standalone table as a consolidated baseline.

## Observed 2Q26 direct source facts

The preserved consolidated source bytes report the following current-quarter three-month values, in KRW million:

| product | 2Q26 revenue |
|---|---:|
| DRAM | 56,982,743 |
| NAND Flash | 21,959,898 |
| Other | 376,105 |
| Total | 79,318,746 |

The direct reconciliation is exact:

`56,982,743 + 21,959,898 + 376,105 = 79,318,746`.

Derived only for cross-checking, those source facts correspond to approximately:

- DRAM: `71.8402%`
- NAND: `27.6856%`
- Other: `0.4742%`

These derived shares do **not** round to the IR chart's certified `73% / 27%` pair; they round to `72% / 28%`. The system therefore records an official-source share-definition mismatch and keeps model-input promotion closed. This mismatch does not erase or rewrite the directly reported OpenDART amounts.

## Source boundary

The collector and verifier:

1. resolve SK hynix through the OpenDART corporation registry;
2. search only the configured filing window;
3. require exactly one non-correction disclosure whose report name is exactly `반기보고서 (2026.06)`;
4. download the original `/api/document.xml` ZIP;
5. archive the exact ZIP bytes and SHA-256 digest;
6. archive the exact parser/source contract used for the capture;
7. bind the certification evidence ID and parser-contract SHA-256 into a chain evidence ID;
8. replay the archived ZIP through the safe OpenDART document parser;
9. refuse truncated normalized text;
10. require a supported KRW unit;
11. require the consolidated `매출액 (연결)` product-revenue scope;
12. support the official `NAND Flash`, `기타`, and `부문 합계` labels;
13. accept the live `수익` row label while retaining historical compatibility aliases;
14. require exactly one `3개월` value for DRAM, NAND, Other, and Total;
15. reconstruct raw HTML/XML `rowspan` and `colspan` geometry;
16. bind a split header table only to its immediately adjacent revenue data table;
17. require normalized-text and structured-table metrics to agree exactly; and
18. require `DRAM + NAND + Other == reported total` within source-unit tolerance.

The older single-table and row-layout parsers remain compatibility fallbacks for regression evidence. Production promotion still requires the consolidated source-first path.

## Failure diagnostics

A failed live parse does not discard its source. After filing discovery and download, a parsing or certification failure preserves a private diagnostic bundle below:

`data/private/research/skhynix-opendart-q2-product-revenue-certification/failed/`

The bundle contains the exact `opendart_document.zip`, `normalized_document.txt`, and `diagnostic.json`. The offline inspection command also creates `table_shape_diagnostic.json`, which inventories normalized-text contexts and raw reconstructed table grids without making another OpenDART request.

## Bound replay

The offline verifier reconstructs `PeriodicProductRevenueSpec` from the archived `parser_contract.json`, not from whatever registry exists later. Contract, ZIP, or normalized-text tampering breaks verification.

A low-level `certification.json` by itself is not a promotion boundary. Production consumers enter through the bound `latest_certification.json` pointer and verifier.

`OPENDART_API_KEY` is read from the environment for live discovery and is never written to artifacts or logs.

## What becomes certified

When the official filing matches the source contract and text/structured replays agree, the chain may certify:

- current 2Q26 DRAM revenue amount;
- current 2Q26 NAND revenue amount;
- current 2Q26 Other product/service revenue amount;
- current 2Q26 consolidated reported product-revenue total;
- exact source-byte archival and source vintage;
- current-quarter three-month semantics;
- internal product-revenue reconciliation; and
- a revenue-only direct product baseline.

These amounts are direct source facts, not outputs of the share-allocation resolver.

## Independent official-IR cross-check

The direct OpenDART amounts are converted to shares only for an independent official-source cross-check. The numeric Other amount comes only from OpenDART and is never derived as `100 - DRAM - NAND` or from chart geometry.

For the observed 2Q26 source facts:

- period identity matches;
- positive Other presence matches;
- DRAM rounded-share identity does not match;
- NAND rounded-share identity does not match; and
- `product_revenue_promotion_ready=false`.

Until the difference in product/share definitions between the two official presentations is independently explained, `semiconductor_direct_product_revenue_model_input_ready=false`.

The directly reported DART source fact remains available and baseline-eligible as revenue evidence; it is not silently discarded merely because the independent IR presentation uses a non-identical share definition.

## Decision-chain integration

The calibrated chain routes:

`accounting identity -> direct product revenue -> derived allocation -> company actual -> ...`

The direct-product layer is explicitly non-scoring. Missing, invalid, ambiguous, or cross-source-conflicting evidence is surfaced as an evidence gap rather than converted into a zero score.

## Gates that remain closed

Even after direct product revenue succeeds:

- `allocation_resolver_registered=false`;
- `product_profitability_certified=false`;
- `full_baseline_certified=false`;
- `numeric_forecast_enabled=false`;
- `fair_value_estimate_enabled=false`;
- `target_price_enabled=false`; and
- `decision_score_enabled=false`.

Product revenue does not certify product gross profit or margin. The forward-model contract still requires revenue plus `gross_profit_or_margin` for additive DRAM/NAND blocks.

## Windows execution

```powershell
cd "C:\Download\쿠쿠\coding\Alpha_Cycle_Lab"
git pull --ff-only
.\scripts\report_skhynix_opendart_q2_product_revenue_certification.ps1
```

The launcher requires `OPENDART_API_KEY` in the process environment. If prior official-IR product-assignment evidence is absent, the launcher rebuilds that local IR evidence chain first.

Successful artifacts are written below:

`data/private/research/skhynix-opendart-q2-product-revenue-certification/`

A successful capture contains at least:

- `opendart_document.zip`
- `normalized_document.txt`
- `certification.json`
- `parser_contract.json`
- `latest_certification.json`
- `latest_product_revenue_readiness.json`

Raw and generated evidence remain private research artifacts and are not committed to Git.
