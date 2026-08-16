# SK hynix 2Q26 OpenDART direct product-revenue certification

## Purpose

The official 2Q26 SK hynix IR chart certifies that the displayed `73%` token belongs to DRAM and `27%` belongs to NAND, while a positive-area `Others` segment remains numerically unlabeled. The IR chart is therefore an independent presentation/comparability check, not a source for `Other=0` or residual allocation.

This stage discovers the official OpenDART `반기보고서 (2026.06)` and certifies current-quarter DRAM, NAND, Other, and Total revenue directly from the periodic filing.

## Live certification closed

The live production path successfully certified receipt `20260814003509` on 2026-08-16. The consolidated filing reports the following current-quarter values in KRW million:

| product | 2Q26 revenue |
|---|---:|
| DRAM | 56,982,743 |
| NAND Flash | 21,959,898 |
| Other | 376,105 |
| Total | 79,318,746 |

The direct source reconciles exactly:

`56,982,743 + 21,959,898 + 376,105 = 79,318,746`.

These are direct source facts. They are not produced by an IR-share allocation, residual, peer substitution, or chart-height inference.

## Actual 2026 filing layout

The preserved filing proves that the consolidated product disclosure cannot be treated as one stable HTML table. Under `21. 매출액 (연결)`, the raw source contains one current-period consolidated product header with the product order:

`DRAM | NAND Flash | 기타 | 부문 합계`

The source may split labels, values, layout tables, and comparative-period markers across presentation elements. Production certification therefore separates **value parsing** from **raw-source structural certification** instead of requiring a second HTML-layout-specific value parser.

## Current production provenance boundary

The collector and verifier now require all of the following:

1. resolve SK hynix through the OpenDART corporation registry;
2. require the exact `반기보고서 (2026.06)` filing in the configured discovery window;
3. archive the exact `/api/document.xml` ZIP bytes and SHA-256;
4. regenerate normalized text from those exact ZIP bytes;
5. archive normalized text and its SHA-256;
6. parse the direct DRAM/NAND/Other/Total amounts from the regenerated normalized text;
7. require the direct product amounts to reconcile exactly to the directly reported company product-revenue total;
8. inspect the raw archive independently and require exactly one current-period consolidated DRAM/NAND/Other/Total structural header;
9. require the raw structural header to carry the same supported KRW unit as the normalized direct values;
10. require at least one accepted raw-source revenue label;
11. bind the exact parser/source contract into a chain evidence ID;
12. replay the archived ZIP during verification rather than trusting a previously parsed JSON scalar; and
13. reject ZIP, normalized-text, contract, period, scope, product-order, unit, or reconciliation ambiguity.

The raw-source structural gate intentionally does **not** rediscover the four amounts from HTML text-token order. OpenDART presentation markup can split values and period markers in unstable ways. A second value-discovery algorithm over the same source bytes created false negatives without adding an independent source. Value provenance remains fail-closed through exact ZIP retention, normalized-text reproduction, direct parsing, exact revenue reconciliation, structural header/unit certification, and parser-contract binding.

No `Other=100-DRAM-NAND`, chart-height allocation, consolidated-margin allocation, hidden residual, or peer substitution is permitted.

## Failure diagnostics and offline preflight

A failed live parse preserves the source under:

`data/private/research/skhynix-opendart-q2-product-revenue-certification/failed/`

The bundle contains the exact ZIP, normalized text, and diagnostic metadata. On the next Windows launcher run, the newest preserved failure bundle is replayed **offline before any new OpenDART request**. The offline preflight regenerates/parses the archived source and stops locally if the current production provenance gate cannot certify it.

The 2026-08-16 live run passed this offline preflight and then completed a new live certification.

## Bound replay

The verifier reconstructs `PeriodicProductRevenueSpec` from archived `parser_contract.json`, not from a later registry state. Capture and verifier import the same production structural parser directly; there is no runtime monkey-patch dependency. Contract, ZIP, or normalized-text tampering breaks verification. A standalone `certification.json` is not a production promotion boundary; consumers enter through the bound pointer and verifier.

## Independent official-IR comparison

The direct OpenDART amounts imply approximately:

- DRAM: `71.8402%`
- NAND: `27.6856%`
- Other: `0.4742%`

Those figures do not reproduce the IR chart's `73% / 27%` labels under ordinary integer rounding. The comparison is therefore classified as:

`official_source_share_identity_mismatch`

This means the two official presentations are not certified as numerically share-identical under the current evidence. It does **not** invalidate the directly reported OpenDART amounts. The direct source fact remains valid and the IR comparison remains diagnostic only.

## Revenue input readiness

A bound, replayable, reconciled OpenDART direct-product certification is sufficient to make the **revenue-only** input available:

`semiconductor_direct_product_revenue_model_input_ready=true`

The live readiness output confirms:

- `company_revenue_reconciliation_certified=true`;
- `product_revenue_baseline_eligible=true`;
- `allocation_resolver_registered=false`; and
- `direct_source_fact_remains_valid=true` despite the IR share-identity mismatch.

## Next blocker: product profitability

The forward-model contract requires `gross_profit_or_margin` for the additive DRAM and NAND blocks. Direct product revenue does not identify those two profitability dimensions.

Current source coverage therefore remains:

- DRAM revenue: direct source fact;
- NAND revenue: direct source fact;
- Other revenue: direct source fact;
- DRAM numeric gross profit/margin: not directly certified;
- NAND numeric gross profit/margin: not directly certified.

Company-level profit cannot be silently allocated by revenue share and promoted to a source fact. Residual allocation and peer-margin substitution are also prohibited as source facts. A separate calibrated-assumption methodology is required unless direct product-level profitability is later disclosed and certified.

## Gates that remain closed

Even though the direct revenue block is model-input-ready:

- `product_profitability_certified=false`;
- `full_baseline_certified=false`;
- `numeric_forecast_enabled=false`;
- `fair_value_estimate_enabled=false`;
- `target_price_enabled=false`; and
- `decision_score_enabled=false`.

The next stage must address product profitability explicitly rather than weakening these gates.

## Windows execution

```powershell
cd "C:\Download\쿠쿠\coding\Alpha_Cycle_Lab"
git pull --ff-only
.\scripts\report_skhynix_opendart_q2_product_revenue_certification.ps1
```

If a preserved failed bundle exists, the same command first runs the offline preflight against that exact source before performing a new official OpenDART capture. The API key is never written to logs or artifacts.
