# KIS forward estimate normalization

This layer converts historically crosschecked KIS `estimate-perform` rows into local forward financial levels without claiming consensus provenance or changing decision scores.

## Evidence chain

The binding is not inferred from row position alone. It is rebuilt from the latest successful local crosscheck artifacts:

- revenue: KIS row historically matched to OpenDART revenue across Samsung Electronics and SK hynix for 2023-2025;
- operating income: same six-observation historical crosscheck;
- net income attributable to owners: separately matched to the exact OpenDART standard account `ifrs-full_ProfitLossAttributableToOwnersOfParent` across the same issuers/years.

The current verified binding is structural:

- each metric has one historically verified `outputN` row and KRW scale;
- `output4.dt` defines the period axis;
- `data1`, `data2`, ... map positionally to the corresponding `output4` entries;
- future snapshots are accepted only if the verified issuers retain the compatible DATA-row shape and a valid increasing actual-to-forecast period axis.

This lets a new KIS snapshot be normalized without rerunning the historical OpenDART crosscheck every time, while still failing closed if the provider shape changes.

## Output

Run:

```powershell
python -m alpha_cycle.kis_forward_estimate_cli
```

The private artifact root is:

```text
data/private/live-research/kis-forward-estimates
```

Files:

- `manifest.json`
- `semantic_binding.json`
- `forward_estimates.csv`
- `forward_summary.csv`
- `latest_kis_forward_estimates.json`

`forward_estimates.csv` contains the verified metrics for every forecast period exposed by `output4`, normalized to KRW. It also records the immediately preceding period and a simple growth rate only when the preceding value is positive. `forward_summary.csv` adds operating margin and owners-of-parent net margin.

## Trust boundary

A successful artifact means:

- the historical row/scale mapping was crosschecked against OpenDART;
- the source KIS snapshot is structurally compatible with that mapping;
- the forward numeric levels were normalized deterministically.

It does **not** mean:

- KIS documented the economic meaning of every DATA row;
- the forward values are a market-wide consensus;
- the estimate producer or aggregation methodology is known;
- a revision series exists from only one snapshot;
- the values are point-in-time backtest certified;
- the values should alter the decision score.

Therefore the artifact keeps:

```text
historical_semantic_crosscheck_verified=true
forward_values_normalized=true
estimate_snapshot_change_available=false
provider_semantics_certified=false
consensus_certified=false
revision_certified=false
point_in_time_backtest_eligible=false
decision_score_enabled=false
```

## Next layer

After at least two distinct normalized KIS snapshots exist, a separate snapshot-change layer can compare common issuer/metric/forecast-period rows. That layer must describe the result as a change in the observed KIS estimate series, not as a consensus revision unless independent provenance establishes consensus semantics.
