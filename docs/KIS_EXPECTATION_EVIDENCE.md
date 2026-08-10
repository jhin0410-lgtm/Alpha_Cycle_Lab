# KIS expectation evidence

Alpha Cycle Lab can collect the Korea Investment & Securities OpenAPI endpoint
`/uapi/domestic-stock/v1/quotations/estimate-perform` (`HHKST668300C0`) as an
optional raw estimate-evidence source.

## Trust boundary

This integration is deliberately classified as:

- provider: `korea_investment_openapi`
- source scope: `kis_estimate_perform_raw_unclassified`
- provider field/provenance semantics certified: **false**
- consensus certified: **false**
- revision certified: **false** until field semantics are verified and multiple time-separated snapshots exist
- catalyst direction scoring: unchanged / disabled by this evidence alone

The official KIS sample names this endpoint `국내주식 종목추정실적[국내주식-187]` and returns four output blocks. That endpoint name and shape alone do not establish whether a field is a KIS-only analyst estimate, an externally aggregated estimate, or another provider-defined statistic. Alpha Cycle Lab therefore does not label the raw feed `single_broker` or `consensus` before the live field layout and authoritative semantics are verified.

## API safety boundary

The implementation uses only:

1. OAuth client-credentials token issuance with `KIS_APP_KEY` and `KIS_APP_SECRET`.
2. The read-only stock estimate-perform endpoint above.

It does **not** require or read a KIS account number and exposes no account, holdings,
balance, order, hash-key, or execution methods.

## First collection

Configure the optional research credentials:

```powershell
.\scripts\setup_kis_research_credentials.cmd
```

Then collect the default Samsung Electronics and SK hynix evidence:

```powershell
.\scripts\collect_kis_expectations.cmd
```

The output is written below:

```text
data/private/live-research/expectation-intelligence/
```

Each immutable content-addressed snapshot contains:

- `manifest.json`
- `structure.csv`
- `records.json`
- `raw_estimate_perform.json`

## Local structure inspection

After a live capture, inspect the newest snapshot without printing any `dataN` estimate values:

```powershell
python -m alpha_cycle.kis_expectation_inventory_cli
```

The inspector validates that consensus/revision/account/order flags remain false, rejects sensitive-looking response keys, and prints only structural information:

- symbol
- output shape and row count
- field names
- `dataN` field names and field count, but never their values
- `output4.dt` period labels
- whether the number of `dataN` fields merely matches the number of period labels

A matching field/period count is only a structural observation. It does **not** certify that `data1` maps to the first `dt`, nor does it assign any output row to revenue, operating profit, EPS, valuation, recommendation, or another financial concept.

## Live structure observation — 2026-08-10

A real read-only capture for `000660` and `005930` established the following shape:

- both symbols: `output1` is one object
- both symbols: `output2` is an array with 6 rows and fields `data1` through `data5`
- `000660`: `output3` has 3 rows with fields `data1` through `data5`
- `005930`: `output3` has 8 rows with fields `data1` through `data5`
- both symbols: `output4` contains 5 `dt` rows: `2023.12`, `2024.12`, `2025.12`, `2026.12E`, `2027.12E`

The differing `output3` row counts across issuers are an additional reason not to assume a fixed row-to-financial-metric mapping.

## Official sample boundary

The Korea Investment official Open Trading API sample for this endpoint is:

```text
examples_llm/domestic_stock/estimate_perform/estimate_perform.py
examples_llm/domestic_stock/estimate_perform/chk_estimate_perform.py
```

The official checker currently maps `data1` through `data5` only to generic `DATA1` through `DATA5`. It explicitly maps `dt` to `결산년월`. Therefore the official sample supports the endpoint identity, four-output structure, generic DATA fields, and the period label meaning, but it does not provide authoritative financial semantics for each DATA row/column.

## Why semantic parsing is deferred

The live response and the official sample both show provider-defined `data1`-`data5` fields without authoritative financial labels. Before assigning financial meanings, Alpha Cycle Lab preserves the raw payload and content hash while exposing only a value-free structural inventory. This prevents an unsupported field interpretation from becoming an investment signal.

The next semantic layer may be added only after authoritative provider semantics are found or an independently verifiable contract can bind the rows and columns. Estimate revisions additionally require at least two independently timestamped snapshots for the same provider/symbol/period/field; one snapshot can never create a revision.
