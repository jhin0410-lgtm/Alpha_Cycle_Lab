# Research Intelligence End-to-End Audit

Audit date: 2026-07-29

Scope:

- OpenDART corporation-code archive
- OpenDART company, full financial statement, and disclosure endpoints
- ECOS `StatisticSearch`
- revision-aware research portal
- immutable snapshot serialization and CLI boundaries

## Findings corrected

| Area | Previous behavior | Risk | Correction |
|---|---|---|---|
| Corporation archive | Any nonblank stock code that was not exactly six digits stopped the whole run | One unrelated dirty row blocked Samsung and SK hynix | Quarantine malformed unrelated rows, normalize safe variants, report counts |
| Duplicate stock codes | Dictionary construction silently chose one row | Stale or wrong corporation code | Select latest `modify_date`; fail on equal-date ambiguity |
| Archive error response | Non-ZIP OpenDART error looked like a corrupt archive | Misdiagnosis and repeated blind fixes | Decode XML status/message before reporting archive corruption |
| Disclosure search | Only the first 100 disclosures were collected | Missing corrections and material filings | Follow `total_page`, deduplicate `rcept_no`, bound maximum pages |
| No disclosure data | Status `013` was treated as a fatal API failure | Valid companies/date ranges failed | Return a typed empty disclosure frame |
| Provider identity | Company/financial and ECOS identifiers were not cross-checked | Wrong-series or wrong-company contamination | Validate returned stock/stat/item codes when present |
| ECOS date policy | UTC retrieval date was used | Korea midnight boundary could shift availability by one day | Use `Asia/Seoul` retrieval date |
| ECOS truncation | Large responses could be accepted without count verification | Silent missing macro observations | Compare `list_total_count` with returned rows |
| ECOS missing cells | One blank value stopped the whole series | Fragile live ingestion | Skip missing cells; fail only if no numeric rows remain |
| Snapshot JSON | pandas/numpy scalar and NaN handling was incomplete | Snapshot ID or manifest creation could fail after APIs succeeded | Normalize numpy scalars and reject non-finite values deterministically |
| Historical boundary | The output was described too broadly as complete PIT data | False confidence in superseded historical revisions | Label `live_endpoint_filtered`, emit warnings, block future disclosures |

## Important remaining limitations

1. Non-December fiscal-year companies are still rejected rather than assigned an
   incorrect period end.
2. The live OpenDART endpoint does not provide a complete archive of every superseded
   correction. Full historical revision reconstruction requires recurring snapshots.
3. ECOS exact historical publication timestamps are not inferred. Retrieval date remains
   the conservative availability boundary.
4. Industry market share, competitor structure, order backlog, and CAPEX evidence are
   separate future adapters.
5. CI uses deterministic fixtures. A local smoke run with the user's official keys is
   still required to verify the current provider payloads and configured ECOS series.

## Acceptance checks

- A malformed unrelated OpenDART stock-code row cannot block valid requested companies.
- Every disclosure page is preserved in raw JSON and normalized without duplicates.
- A conflicting requested corporation code fails explicitly.
- ECOS cannot silently truncate or mix a different configured series.
- Snapshot JSON is deterministic for pandas/numpy scalar types.
- No secret, account, or order endpoint is introduced.
