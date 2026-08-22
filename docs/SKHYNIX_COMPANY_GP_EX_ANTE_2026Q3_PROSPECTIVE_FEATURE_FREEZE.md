# SK hynix 2026Q3 prospective feature freeze

## Boundary

The historical model-development round is closed. The frozen chronological backtest selected
`lagged_gp_affine_ols`, and the selected estimator was then deterministically refit on all
20 locked historical rows. This stage cannot change that model.

The frozen forecast protocol defines the 2026Q3 forecast origin as **2026-08-31 23:59:59
Asia/Seoul** (`quarter_end_minus_30_calendar_days`). The selected model requires exactly one
predictor: `lagged_company_gross_profit`. For 2026Q3 that predictor is the reported SK hynix
company gross profit for 2026Q2.

## Source semantics

No new accounting interpretation is introduced here. The prospective source parser inherits
from the already locked historical execution v2:

- OpenDART `fnlttSinglAcntAll`, CFS,
- 2026 half-year report code `11012`,
- `thstrm_amount`,
- IS/CIS statement divisions,
- the already frozen legacy/new IFRS account-id aliases,
- one common filing receipt for Revenue, Cost of Sales, and Gross Profit,
- direct `Revenue - Cost of Sales = Gross Profit` identity.

Fuzzy account-name matching, arithmetic reconstruction of a missing Gross Profit account,
source fallback, correction selection, and post-capture source refresh are prohibited.

## Early-lock rule

The first live 2026Q2 OpenDART payload must be captured no later than the forecast origin.
The raw payload is written to a content-addressed SHA-256 archive **before** feature
extraction. That first capture is final for this 2026Q3 forecast. Information or amendments
arriving after the first capture are not incorporated.

If no source capture exists and the 2026Q3 origin has already passed, this code refuses a new
2026Q3 capture and the frozen protocol falls back to 2026Q4. If a valid pre-origin raw capture
already exists, later parser/replay work may use those exact bytes without re-querying the
source.

## Protected outcome

This stage does not request or inspect any 2026Q3 realized company result. After a successful
feature freeze:

- `prospective_feature_vector_frozen = true`
- `prospective_forecast_run = false`
- `2026q3_target_read = false`
- `2026q3_source_outcome_loaded = false`
- `2026q3_evaluated = false`
- `numeric_forward_forecast_enabled = false`

Only after this immutable prospective feature artifact exists may a later stage apply the
already frozen estimator coefficients to produce the numeric 2026Q3 forecast.
