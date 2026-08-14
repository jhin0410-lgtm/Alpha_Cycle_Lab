# SK hynix SEC Post-Earnings All-Form Inventory

This research tool broadens source discovery without changing the existing version-1 `6-K`
scout evidence semantics.

## Why it exists

The verified `6-K` scout captured seven SK hynix filings after 2026-07-29 and all seven were
classified `no_product_mix_signal`. One filing contained a Q2 period anchor, but none contained
DRAM, NAND, Other-products, or revenue anchors. The next safe source-discovery step is therefore
to inspect other SEC primary HTML filing forms rather than silently widening the established
`6-K` classifier.

## Scope

The inventory:

1. downloads the official SK hynix SEC submissions JSON,
2. discovers every primary HTML filing after the configured cutoff and no later than the
   observed date, regardless of form,
3. archives each exact primary HTML document,
4. classifies broad Q2, DRAM, NAND, Other-products, and revenue anchors,
5. persists form counts and candidate accessions,
6. immediately reverifies the archived submissions and filing bytes before printing results.

Examples of forms that may be encountered include `6-K`, `424B4`, `F-1/A`, `FWP`, or other
SEC forms whose primary document is HTML. The inventory does not assume any of those forms is
product-baseline evidence merely because it exists.

## Trust boundary

Every result remains:

- `discovery_only=true`
- `product_baseline_eligible=false`
- `allocation_resolver_registered=false`
- `numeric_forecast_enabled=false`
- `decision_score_enabled=false`

A candidate still requires a dedicated source/parser contract, period semantics, accounting
reconciliation, archived-byte verification, and a separate allocation-resolver change before it
can affect the model.

The existing `sec-post-earnings-product-mix-scout` artifacts are not rewritten or reclassified.

## Windows usage

With the project environment and SEC User-Agent already configured:

```powershell
.\scripts\inventory_sec_post_earnings_all_forms.ps1
```

The output includes:

- `filing_count`
- `non_6k_filing_count`
- `form_counts`
- `classification_counts`
- `candidate_count`
- `candidate_accessions`
- filing-level form and anchor flags

Artifacts are written under:

```text
data/private/research/sec-post-earnings-all-form-inventory
```
