# Generic Prospective Forecast Ledger

## Purpose

The Forecast Ledger is the first implementation layer under the Decision System v2.1
forecast-governance guardrail.

It is not a forecasting model. It is infrastructure for preserving what was forecast, when it
was knowable, what later happened, and how the forecast performed without hindsight mutation.

The first schema deliberately supports numeric point forecasts only. More forecast forms can be
added only through a successor schema rather than by weakening the current contract.

## Three immutable objects

```text
ForecastRegistrationSnapshot
        ↓
ForecastOutcomeSnapshot
        ↓
ForecastEvaluationSnapshot
```

They are separate content-addressed objects.

A registration is never updated with an actual. An outcome is never written back into a forecast.
An evaluation references both immutable snapshot ids.

## Registration

A registration stores at least:

- original registration time;
- generic-ledger recording time;
- forecast origin;
- information cutoff;
- security and target identity;
- target date and horizon label;
- point forecast and unit;
- optional predeclared range/direction;
- ordinal confidence with rationale;
- model/human/consensus/benchmark identity;
- model family;
- driver references and regime tags;
- decision relevance and difficulty;
- preregistered baseline snapshot references;
- dependency cluster;
- immutable source evidence ids;
- primary error metric;
- Decision System v2.1 guardrail evidence id.

No composite forecast score is enabled.

## Native registration versus imported frozen evidence

Two registration modes exist.

### `native_prospective`

The generic ledger itself records the forecast no later than the forecast origin.

### `external_frozen_reference`

A forecast may have been prospectively frozen by an older dedicated research contract before the
generic ledger existed. The ledger can reference that immutable evidence later.

The schema preserves both:

- `registered_at`: when the original forecast was actually frozen;
- `ledger_recorded_at`: when the generic ledger representation was created.

This prevents a later import from being misrepresented as a historical generic-ledger record.

## SK hynix 2026Q3 integration boundary

The already-frozen SK hynix company-gross-profit forecast is used only as a reference/integration
fixture.

Locked selected forecast:

- target: `company_gross_profit_krw_million`
- target period: 2026Q3
- target date: 2026-09-30
- forecast: `73,030,702.00644387 KRW million`
- forecast evidence id:
  `1fd34ba0f43bc2fbc296a6823f2f313296955d8a3860994b7757eb6e23dad468`
- feature evidence id:
  `139d50940b27582dbaa9206989439c7b9253d75d65e12e45bcb7a14512214bda`
- selected-estimator evidence id:
  `4ddf0e7206fcbb6a58ba2e7fcb93b48bf79195171dfc96a894481dbfa612a2d1`
- original lock time: 2026-08-22 16:52:07.618525 KST
- forecast origin: 2026-08-31 23:59:59 KST

Its persistence benchmark is represented as a separate forecast registration:

- `65,991,356.0 KRW million`
- model family: previous-reported-quarter gross-profit persistence.

Both forecasts share the dependency cluster:

`SKHYNIX_MEMORY_EARNINGS_2026Q3`

Therefore two forecast rows do **not** imply two independent pieces of economic evidence.

The extreme OOD warning on the selected forecast remains unchanged. The generic ledger does not
repair, refit, relabel, or replace the frozen research round.

## Target-level outcomes

An actual is a property of the target, not of one forecasting model.

For this reason `ForecastOutcomeSnapshot` is target-level and contains no registration id.

Comparable selected models, benchmarks, human forecasts, and consensus forecasts all evaluate
against the same immutable outcome snapshot. This is required for a coherent Forecast Tournament.

## Evaluation

The first evaluation rule is `numeric-point-v1`.

It records:

- signed error = forecast - actual;
- absolute error;
- squared error;
- absolute percentage error when defined;
- optional direction correctness;
- optional predeclared-range coverage;
- the preregistered primary error metric.

Single-forecast evaluation explicitly does not claim calibration. Calibration requires a prospective
history rather than one realization.

If a preregistered baseline evaluation is available for the exact same target outcome, the ledger may
record:

`baseline absolute error - forecast absolute error`

Positive means the forecast beat that baseline on absolute error.

A baseline cannot be attached after the outcome unless its registration snapshot id was already in
`baseline_refs`.

## Performance vector

The v2.1 policy freezes these dimensions:

```text
accuracy
calibration
decision_relevance
information_gain
difficulty
```

The ledger preserves them as separate diagnostics.

It does not create a weighted score from them.

## Dependency clusters

Forecast records must declare `dependency_cluster_id`.

The first summary reports both:

- raw forecast count;
- unique dependency-cluster count.

It does **not** claim that the unique-cluster count is a statistically estimated effective sample
size. That would require a later, justified dependence model.

## Persistence

Registrations, outcomes, and evaluations are stored under separate immutable roots:

```text
<output-root>/registration/
<output-root>/outcome/
<output-root>/evaluation/
```

Each immutable directory contains a manifest plus the object payload. Mutable `latest_*` files are
pointers only.

No object enables an order API.

## What this PR intentionally does not build

- no forecast generation;
- no outcome polling;
- no automatic evaluation scheduler;
- no probability calibration;
- no model ranking weights;
- no statistical ESS claim;
- no architecture change based on one forecast;
- no target price or portfolio allocation;
- no modification of the SK hynix 2026Q3 dedicated scorer.

## Next integration gate

After this ledger is stable, the next architecture unit should implement the independent
`CounterThesisSnapshot` and `BlindSpotDiscoverySnapshot` contracts required by v2.1.

The parked forward-valuation PR remains useful, but should be revalidated only after those epistemic
objects are in place, as specified by the current development sequence.
