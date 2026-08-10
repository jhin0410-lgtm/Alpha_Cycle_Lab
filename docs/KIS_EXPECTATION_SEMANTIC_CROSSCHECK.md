# KIS estimate-perform semantic crosscheck

This layer attempts to identify selected KIS `estimate-perform` DATA rows by comparing the historical actual portion of the KIS matrix with already-captured OpenDART valuation history.

It is a **cross-source semantic identification diagnostic**, not provider documentation and not investment scoring.

## Inputs

The default local inputs are:

```text
data/private/live-research/expectation-intelligence/
data/private/live-research/valuation-intelligence/
```

The KIS snapshot must remain:

- `source_scope = kis_estimate_perform_raw_unclassified`
- `semantic_status = raw_structure_only`
- `consensus_certified = false`
- `revision_certified = false`
- account / holdings / balance / order APIs disabled

The valuation snapshot supplies normalized OpenDART annual values for:

- revenue
- operating income
- net income

## Why comparative prior-year values are used

For an evaluation date in 2026, the default three-year valuation window begins in 2024. A separate 2023 FY row may therefore not exist in `financial_history.csv`.

OpenDART annual rows also preserve the comparative prior-year amount. The crosscheck consequently prefers:

1. the following year's FY `*_prior_same` amount for a historical year;
2. the direct FY current amount only when the following comparative amount is unavailable.

With the current KIS period axis this normally means:

```text
2023 actual -> 2024 FY prior_same
2024 actual -> 2025 FY prior_same
2025 actual -> 2025 FY current
```

This policy intentionally favors the later comparative presentation, which may reflect a restatement. It is current cross-source semantic evidence, **not point-in-time historical evidence**.

## Identification method

The live KIS response currently exposes five generic DATA fields and five period labels:

```text
data1 data2 data3 data4 data5
2023.12 2024.12 2025.12 2026.12E 2027.12E
```

The code does not assume this positional mapping in advance.

For every shared row in `output2` and `output3`, and for each target OpenDART metric, the crosscheck evaluates:

- every permutation assigning actual years to DATA fields;
- several explicit KRW scale candidates;
- both Samsung Electronics (`005930`) and SK hynix (`000660`);
- all three actual years.

A historical semantic candidate is verified only when:

- all six issuer-year observations are present;
- the best mapping is the positional mapping implied by the period axis;
- maximum relative error is at most `0.5%`;
- the next-best mapping has mean relative error of at least `1.0%`.

These thresholds are conservative identification guards, not return-fitted investment thresholds.

## Output boundary

Run:

```powershell
python -m alpha_cycle.kis_expectation_semantic_crosscheck_cli
```

Artifacts are written below:

```text
data/private/live-research/kis-expectation-semantic-crosscheck/
```

The public CLI output and `crosscheck.json` report:

- source snapshot IDs
- matched output and row number
- metric candidate
- inferred scale to KRW
- year-to-DATA-field mapping
- fit errors
- actual-reference provenance path

They do **not** publish KIS forecast values.

Even after a historical match:

- `provider_semantics_certified = false`
- `consensus_certified = false`
- `revision_certified = false`
- `point_in_time_backtest_eligible = false`
- `forecast_values_published = false`
- `decision_score_enabled = false`

A successful historical crosscheck is only evidence that a provider row behaves consistently with an OpenDART metric across the tested companies and years. It does not prove who produced the estimate, whether it is multi-broker consensus, or whether future-period values should enter an investment score.
