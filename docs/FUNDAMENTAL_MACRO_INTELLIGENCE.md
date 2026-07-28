# Fundamental and Macro Intelligence

This layer collects official OpenDART financial/disclosure data and Bank of Korea
ECOS macro series into one content-addressed, point-in-time snapshot.

## Trust boundaries

- Credentials are read only from `OPENDART_API_KEY` and `ECOS_API_KEY`.
- Only `https://opendart.fss.or.kr` and `https://ecos.bok.or.kr/api` are allowed.
- The adapters expose GET-only data access and no broker/order methods.
- Secrets and full request URLs are excluded from errors and artifacts.
- OpenDART `available_date` is the filing receipt date encoded in `rcept_no`.
- ECOS does not expose a vintage release timestamp in `StatisticSearch`; the first
  implementation conservatively sets `available_date` to the local retrieval date.
  It therefore does not pretend that historical ECOS observations were known earlier.

## Current financial scope

- Listed Korean companies resolved through the official OpenDART corporation-code ZIP.
- Full single-company financial statements from `fnlttSinglAcntAll.json`.
- Consolidated (`CFS`) or separate (`OFS`) statements.
- December fiscal-year companies only. Non-December fiscal years fail closed until a
  calendar-aware period-end implementation is added.
- Current-term numeric facts are normalized to the existing revision-aware financial
  contract. Blank/non-numeric current-term cells are omitted but remain in raw JSON.

## ECOS configuration

Copy `config/ecos_series.example.yaml` and explicitly select statistical table,
cycle, date range, and item-code path. Series IDs must be unique.

## CLI

```powershell
$env:OPENDART_API_KEY="<local key>"
$env:ECOS_API_KEY="<local key>"

python -m alpha_cycle.research_cli `
  --symbols 005930,000660 `
  --business-year 2025 `
  --report-code 11011 `
  --fs-div CFS `
  --disclosure-begin 2025-01-01 `
  --disclosure-end 2026-07-28 `
  --evaluation-date 2026-07-28 `
  --revision-policy latest_known `
  --ecos-config config/ecos_series.local.yaml `
  --market-snapshot data/private/market-intelligence/<snapshot-directory> `
  --output data/private/research-intelligence
```

The output directory contains `financials.csv`, `disclosures.csv`, `macro.csv`,
provider raw JSON, and a manifest binding the optional market snapshot ID.
