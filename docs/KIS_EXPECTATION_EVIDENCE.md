# KIS expectation evidence

Alpha Cycle Lab can collect the Korea Investment & Securities OpenAPI endpoint
`/uapi/domestic-stock/v1/quotations/estimate-perform` (`HHKST668300C0`) as an
optional research-evidence source.

## Trust boundary

This integration is deliberately classified as:

- provider: `korea_investment_openapi`
- source scope: `single_broker_research_estimate`
- consensus certified: **false**
- revision certified: **false** until multiple time-separated snapshots are available
- catalyst direction scoring: unchanged / disabled by this evidence alone

The endpoint is a Korea Investment research estimate feed. It must not be renamed or
presented as multi-broker market consensus.

## API safety boundary

The implementation uses only:

1. OAuth client-credentials token issuance with `KIS_APP_KEY` and `KIS_APP_SECRET`.
2. The read-only stock research endpoint above.

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

## Why semantic parsing is deferred

The official sample exposes four output blocks and generic `data1`-`data5` fields.
Before assigning financial meanings, Alpha Cycle Lab first captures a real provider
response, its SHA-256, output shapes, and `output4.dt` period labels. This prevents a
misread field layout from becoming an investment signal.

The next semantic layer may be added only after the real response structure is
validated. Estimate revisions require at least two independently timestamped snapshots
for the same provider/symbol/period/field; one snapshot can never create a revision.
