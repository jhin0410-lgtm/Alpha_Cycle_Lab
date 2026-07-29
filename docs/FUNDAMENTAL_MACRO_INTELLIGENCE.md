# Fundamental and Macro Intelligence

This layer collects official OpenDART financial/disclosure data and Bank of Korea
ECOS macro series into one content-addressed research snapshot.

## Trust boundaries

- Credentials are read only from `OPENDART_API_KEY` and `ECOS_API_KEY`.
- Only `https://opendart.fss.or.kr` and `https://ecos.bok.or.kr/api` are allowed.
- The adapters expose GET-only data access and no broker/order methods.
- Secrets and full credential-bearing request URLs are excluded from errors and artifacts.
- OpenDART financial `available_date` uses the filing receipt date.
- ECOS availability uses the Korea (`Asia/Seoul`) retrieval date because
  `StatisticSearch` does not provide an authoritative historical release timestamp.
- The manifest labels this workflow `live_endpoint_filtered`. It does not claim that
  superseded OpenDART corrections or historical ECOS vintages can be reconstructed
  before the project has collected and archived them.

## OpenDART hardening

The corporation-code ZIP contains the whole disclosure universe, not only the requested
companies. Unlisted rows are ignored. A malformed unrelated listed row is quarantined
and counted instead of terminating the entire archive.

- Five-digit numeric values and `A`-prefixed six-digit codes are normalized safely.
- Invalid unrelated stock-code or metadata rows are skipped and reported in
  `corp_code_archive` diagnostics.
- Duplicate stock codes are resolved by the newest `modify_date`.
- Equal-date conflicts between different corporation codes fail only for the affected
  requested stock code.
- XML error responses returned instead of ZIP files are decoded into actionable errors.
- Disclosure search follows every page, deduplicates receipt numbers, and treats
  OpenDART status `013` as a valid empty disclosure result.

## Financial scope

- Listed Korean companies resolved through the official corporation-code ZIP.
- Full single-company financial statements from `fnlttSinglAcntAll.json`.
- Consolidated (`CFS`) or separate (`OFS`) statements.
- December fiscal-year companies only.
- Current-term numeric facts are normalized to the revision-aware financial contract.
- Company and financial-row stock codes are cross-checked against the resolved request.

## ECOS scope

Copy `config/ecos_series.example.yaml` and explicitly select the statistical table,
cycle, date range, and item-code path.

The adapter validates:

- cycle-specific start and end formats and ordering;
- returned statistic and item-code identity when ECOS supplies those fields;
- response row counts so truncation is not accepted silently;
- duplicate timestamps, which usually mean the item-code path is not specific enough;
- missing numeric cells, which are skipped while complete absence still fails.

## CLI

Use the current Korea date for a live macro snapshot. Historical dates are accepted,
but may yield empty ECOS rows and a warning because availability is deliberately
conservative.

```powershell
$env:OPENDART_API_KEY="<local key>"
$env:ECOS_API_KEY="<local key>"

python -m alpha_cycle.research_cli `
  --symbols "005930,000660" `
  --business-year 2025 `
  --report-code 11011 `
  --fs-div CFS `
  --disclosure-begin 2025-01-01 `
  --disclosure-end 2026-07-29 `
  --evaluation-date 2026-07-29 `
  --revision-policy latest_known `
  --ecos-config config/ecos_series.local.yaml `
  --market-snapshot data/private/market-intelligence/<snapshot-directory> `
  --output data/private/research-intelligence
```

The output contains `financials.csv`, `disclosures.csv`, `macro.csv`, provider raw
JSON, and a manifest binding the optional market snapshot ID. The CLI also prints
archive diagnostics and any historical-coverage warnings.
