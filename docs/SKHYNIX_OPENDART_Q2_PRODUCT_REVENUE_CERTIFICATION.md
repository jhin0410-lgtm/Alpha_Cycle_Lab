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
6. replays those bytes through the same safe OpenDART document parser;
7. refuses truncated normalized text;
8. requires an explicit KRW unit and explicit `3개월` / `누적` column semantics;
9. requires direct DRAM, NAND, Other, and Total rows in one candidate table; and
10. requires `DRAM + NAND + Other == reported total` within the source's integer-unit tolerance.

No receipt number is hard-coded. `OPENDART_API_KEY` is read from the environment by the existing provider and is never written to artifacts or logs.

## What may become certified

If the official filing matches the registered parser contract, the artifact may certify:

- current 2Q26 DRAM revenue amount;
- current 2Q26 NAND revenue amount;
- current 2Q26 Other product/service revenue amount;
- current 2Q26 reported product-revenue total;
- exact raw source-byte archival;
- exact filing vintage/receipt identity;
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

If the independent official sources disagree, the OpenDART source artifact remains available for diagnosis but product-revenue promotion is blocked until the scope difference is explained.

## Gates that remain closed

Even after direct product revenue succeeds:

- `allocation_resolver_registered=false` — no allocation is required for direct source facts;
- `product_profitability_certified=false` — the filing does not create DRAM/NAND gross-profit facts;
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

The raw ZIP remains private research evidence and is not committed to Git.
