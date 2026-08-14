# SK hynix SEC Post-Earnings Product-Mix Scout

This tool removes a manual source-discovery bottleneck without weakening the model trust
boundary.

## Purpose

After the 2026-07-29 SK hynix 2Q26 company-level provisional filing, additional SEC `6-K`
filings may contain product-level information that is more useful than the company totals.
The scout:

1. downloads the official SK hynix SEC submissions JSON,
2. discovers every `6-K` filed after the configured cutoff and no later than the observed
   date,
3. downloads each exact primary HTML document from the official SEC archive,
4. archives the raw submissions JSON and raw filing HTML bytes,
5. classifies visible-text anchors for Q2, DRAM, NAND, Other products, and revenue,
6. emits candidate accessions for manual parser/source-contract review.

It does **not** parse candidate numbers into the semiconductor baseline.

## Candidate classes

- `no_product_mix_signal`: no memory/product-mix anchor detected.
- `memory_mentions_only`: DRAM/NAND/Other is mentioned but no Q2 product-mix context is
  established.
- `q2_memory_candidate`: a Q2 period anchor plus both DRAM and NAND are present.
- `q2_full_revenue_candidate`: Q2 + DRAM + NAND + Other-products + revenue anchors are all
  present.

The last two classes are only `candidate_for_manual_parser_review=true`. They remain:

- `product_baseline_eligible=false`
- `allocation_resolver_registered=false`
- `numeric_forecast_enabled=false`
- `decision_score_enabled=false`

A candidate must still receive a separate parser, exact accounting-period/source semantics,
archived-byte verification, and a dedicated allocation-resolver PR before it can affect the
model.

## Windows usage

Configure a declared SEC EDGAR User-Agent locally:

```powershell
$env:SEC_EDGAR_USER_AGENT = "AlphaCycleLab your-email@example.com"
```

Run the scout:

```powershell
.\scripts\scout_sec_post_earnings_product_mix.ps1
```

The default cutoff is `2026-07-29`. The observed date defaults to the current Korea date.
Artifacts are written under:

```text
data/private/research/sec-post-earnings-product-mix-scout
```

The output includes the exact candidate accession numbers and archived primary document
bytes. The command is intentionally a research one-shot and is not part of the live
decision pipeline.
