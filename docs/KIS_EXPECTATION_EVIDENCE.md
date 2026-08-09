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

After a live capture, inspect the newest snapshot without printing numeric estimate values:

```powershell
python -m alpha_cycle.kis_expectation_inventory_cli
```

The inspector validates that consensus/revision/account/order flags remain false, rejects sensitive-looking response keys, and prints only:

- symbol
- output shape and row count
- field names
- public `data1` row labels
- public `dt` period labels

This is enough to bind the real response structure without exposing credentials or prematurely assigning the `data2`-`data5` columns to financial periods.

## Why semantic parsing is deferred

The official sample exposes four output blocks, while the current API response contract uses provider-defined fields such as `data1`-`data5`. Before assigning financial meanings, Alpha Cycle Lab first captures a real provider response, its SHA-256, output shapes, row labels, and `output4.dt` period labels. This prevents an unsupported field interpretation from becoming an investment signal.

The next semantic layer may be added only after the live response structure is validated against authoritative provider semantics. Estimate revisions additionally require at least two independently timestamped snapshots for the same provider/symbol/period/field; one snapshot can never create a revision.
