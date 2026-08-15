# SK hynix 2Q26 OpenDART direct product-revenue certification

## Purpose

The official 2Q26 SK hynix IR chart certifies that the displayed `73%` token belongs to DRAM and `27%` belongs to NAND, while a positive-area `Others` segment remains numerically unlabeled. The IR chart is therefore an independent semantic cross-check, not a source for `Other=0` or residual allocation.

This stage discovers the official OpenDART `반기보고서 (2026.06)` and attempts to certify current-quarter DRAM, NAND, Other, and Total revenue directly from the periodic filing.

## Actual filing layout

The live 2026 run exposed an incorrect assumption in the first parser: SK hynix periodic filings do not necessarily place DRAM/NAND/Other/Total in separate data rows.

The official SK hynix half-year filing layout uses product categories as column groups under the consolidated revenue note:

`DRAM | NAND Flash | 기타 | 부문 합계`

Each product group contains `3개월` and `누적` subcolumns, followed by one `수익(매출액)` data row. The production parser therefore reads the current-period `3개월` value from each product column rather than treating products as rows.

The filing can also contain a second product-revenue table for the separate financial statements. The product-column production path therefore requires the nearest revenue-note heading to be `매출액 (연결)` and rejects a standalone-only table as a current consolidated baseline.

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
11. require the consolidated `매출액 (연결)` product-revenue scope for the product-column path;
12. support the official `NAND Flash` and `부문 합계` labels as well as compatibility aliases;
13. require exactly one `3개월` value for DRAM, NAND, Other, and Total in the current-period product table;
14. reconstruct raw HTML/XML `rowspan` and `colspan` geometry and independently recover the same four values;
15. require normalized-text and structured-table metrics to agree exactly; and
16. require `DRAM + NAND + Other == reported total` within the source-unit tolerance.

The older row-layout parser remains only as a compatibility fallback for existing synthetic regression fixtures. The live CLI is routed through the source-first capture module built for the product-column layout.

## Failure diagnostics

A failed live parse no longer discards the source that caused the failure. After the filing has been successfully discovered and downloaded, a parsing/certification failure preserves a private diagnostic bundle below:

`data/private/research/skhynix-opendart-q2-product-revenue-certification/failed/`

The bundle contains the exact `opendart_document.zip`, `normalized_document.txt`, and `diagnostic.json` with receipt identity, source hashes, source URL, and the parser exception. This allows a source-shape failure to be repaired from archived official bytes instead of repeatedly guessing against the API.

## Bound replay

The offline verifier reconstructs `PeriodicProductRevenueSpec` from the archived `parser_contract.json`, not from whatever registry exists later. A future YAML label change therefore cannot silently reinterpret an old source artifact. Contract, ZIP, or normalized-text tampering breaks verification.

A low-level `certification.json` by itself is not a promotion boundary. Production consumers enter through the bound `latest_certification.json` pointer and verifier.

No receipt number is hard-coded. `OPENDART_API_KEY` is read from the environment and is never written to artifacts or logs.

## What may become certified

If the official filing matches the source contract and text/structured replays agree, the chain may certify:

- current 2Q26 DRAM revenue amount;
- current 2Q26 NAND revenue amount;
- current 2Q26 Other product/service revenue amount;
- current 2Q26 consolidated reported product-revenue total;
- exact source-byte archival and source vintage;
- parser/source-contract provenance;
- current-quarter three-month semantics;
- internal product-revenue reconciliation; and
- a revenue-only product baseline.

These amounts are direct source facts, not outputs of the share-allocation resolver.

## Independent official-IR cross-check

When the existing official-IR product-assignment artifact is available, the direct OpenDART amounts are converted to shares only for an independent cross-check:

- DRAM share must round to the certified IR `73%` label;
- NAND share must round to the certified IR `27%` label; and
- a positive direct Other amount must agree with the visible IR Others segment.

The numeric Other amount comes only from the filing row/column value. It is never derived as `100 - DRAM - NAND` and is never inferred from chart geometry.

If the official sources disagree, `semiconductor_direct_product_revenue_model_input_ready=false` until the scope difference is explained.

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
