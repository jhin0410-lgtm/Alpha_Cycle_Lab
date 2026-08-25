# Live Typed Research Round v2.1

The runner connects already-persisted market and official research snapshots to the existing
Decision System v2.1 intake, thesis preflight, package assembler, and Observatory. It does not
collect data, certify a provider, create valuation authority, or enable execution.

## Prospective

Use the two writer-created snapshot directories from the same market/research generation:

```powershell
alpha-cycle-live-typed-research prospective `
  --artifact-root C:\path\to\artifacts `
  --market-source-directory C:\path\to\artifacts\market-intelligence\SNAPSHOT `
  --research-source-directory C:\path\to\artifacts\research-intelligence\SNAPSHOT `
  --evaluation-date 2026-08-14 `
  --research-cutoff-at 2026-08-14T07:18:00+00:00 `
  --processed-at 2026-08-14T07:19:00+00:00 `
  --request-id live-20260814 `
  --run-id live-20260814-run `
  --round-id live-20260814-round `
  --security-id 000660 `
  --security-id 005930 `
  --requested-lane deep `
  --request-text "Persisted-source research round for 000660 and 005930."
```

## Replay

Replay accepts only an explicit frozen manifest. Source-directory arguments are rejected and no
network collector is called:

```powershell
alpha-cycle-live-typed-research replay `
  --artifact-root C:\path\to\artifacts `
  --manifest-path C:\path\to\artifacts\live_typed_source_manifest_v2_1\MANIFEST.json `
  --processed-at 2026-08-14T07:20:00+00:00 `
  --request-id replay-20260814 `
  --run-id replay-20260814-run `
  --round-id replay-20260814-round `
  --security-id 000660 `
  --security-id 005930 `
  --requested-lane deep `
  --request-text "Frozen no-network replay."
```

Both modes print JSON and persist the same payload content-addressed under
`live_typed_research_round_v2_1`. A result with `ready: false` is successful fail-closed
operation when the assembler reports missing underwriting, payoff, expectation, or Decision View
evidence. Such a result does not publish an opportunity set or research round.
