# SK hynix 2Q26 OpenDART direct product-revenue certification

## Purpose

The official 2Q26 SK hynix IR chart now certifies that the displayed `73%` token belongs to DRAM and `27%` belongs to NAND, while a positive-area `Others` segment remains numerically unlabeled. That chart is therefore useful as an independent semantic cross-check, but it is not a complete numeric product mix and must not be converted into `Other=0` or a residual allocation.

This stage instead discovers the official OpenDART `반기보고서 (2026.06)` and attempts to certify the current-quarter three-month DRAM, NAND, Other, and Total revenue amounts directly from the periodic filing.

## Source boundary

The collector:

1. resolves SK hynix through the OpenDART corporation registry;
2. searches only the configured filing window;
3. requires exactly one non-correction disclosure whose report name is exactly `반기보고서 (2026.06)`;
4. downloads the original `/api/document.xml` ZIP exactly once;
5. archives the exact ZIP bytes and SHA-256 digest;
6. archives the exact parser/source contract used for that capture;
7. binds the certification evidence ID and parser-contract SHA-256 into a separate chain evidence ID;
8. replays the archived ZIP through the same safe OpenDART document parser;
9. refuses truncated normalized text;
10. requires an explicit KRW unit and explicit `3개월` / `누적` column semantics;
11. requires direct DRAM, NAND, Other, and Total rows in one unique candidate table; and
12. requires `DRAM + NAND + Other == reported total` within the source's integer-unit tolerance.

The offline verifier reconstructs the `PeriodicProductRevenueSpec` from the archived `parser_contract.json`, not from whatever registry happens to exist later. A future YAML label/anchor change therefore cannot silently reinterpret an old source artifact. Contract tampering breaks the parser-contract hash and chain evidence ID.

No receipt number is hard-coded. `OPENDART_API_KEY` is read from the environment by the existing provider and is never written to artifacts or logs.

## What may become certified

If the official filing matches the bound parser contract, the artifact may certify:

- current 2Q26 DRAM revenue amount;
- current 2Q26 NAND revenue amount;
- current 2Q26 Other product/service revenue amount;
- current 2Q26 reported product-revenue total;
- exact raw source-byte archival;
- exact filing vintage/receipt identity;
- exact parser/source-contract provenance;
- current-quarter three-month period semantics;
- internal product-revenue reconciliation; and
- a **revenue-only product baseline**.

The direct amounts are source facts. They are not outputs of the share-allocation resolver.

## Independent official-IR cross-check

When the existing official-IR product-assignment artifact is available, the direct OpenDART amounts are converted to derived shares only for a cross-check:

- the directly calculated DRAM share must round to the certified IR `73%` label;
- the directly calculated NAND share must round to the certified IR `27%` label; and
- a positive direct Other amount must agree with the visible IR Others segment.

This derived-share calculation does **not** turn the IR chart into a numeric Other source. The numeric Other amount comes only from the direct OpenDART row.

If the independent official sources disagree, the OpenDART source artifact remains available for diagnosis but `semiconductor_direct_product_revenue_model_input_ready=false` until the scope difference is explained.

## Decision-chain integration

The final calibrated chain now routes:

`accounting identity -> direct product revenue -> derived allocation -> company actual -> ...`

For SK hynix the direct-product layer exposes verified DRAM/NAND/Other/Total revenue amounts to scorecards, decision records, and the Markdown report. It is explicitly non-scoring. Missing or invalid direct-product evidence is surfaced as an evidence gap rather than converted into a zero factor score.

The legacy derived-allocation layer remains downstream as a separate fallback/diagnostic evidence type. Direct OpenDART source facts do not require an allocation resolver.

## Gates that remain closed

Even after direct product revenue succeeds:

- `allocation_resolver_registered=false` — no allocation is required for direct source facts;
- `product_profitability_certified=false` — the filing does not create DRAM/NAND gross-profit facts;
- `full_baseline_certified=false`;
- `numeric_forecast_enabled=false`;
- `fair_value_estimate_enabled=false`;
- `target_price_enabled=false`; and
- `decision_score_enabled=false`.

The existing forward-model contract requires revenue **and** `gross_profit_or_margin` for the additive DRAM and NAND blocks. Therefore this stage closes the revenue split gap but does not by itself certify the full operating model.

## Windows execution

```powershell
cd "C:\Download\쿠쿠\coding\Alpha_Cycle_Lab"
git pull --ff-only
.\scripts\report_skhynix_opendart_q2_product_revenue_certification.ps1
```

The launcher requires `OPENDART_API_KEY` to already exist in the process environment. If the prior official-IR product-assignment pointer is absent, the launcher first rebuilds that local evidence chain.

Primary outputs are written below:

`data/private/research/skhynix-opendart-q2-product-revenue-certification/`

A successful capture contains at least:

- `opendart_document.zip`
- `normalized_document.txt`
- `certification.json`
- `parser_contract.json`
- `latest_certification.json`
- `latest_product_revenue_readiness.json`

The raw ZIP and generated evidence remain private research artifacts and are not committed to Git.
