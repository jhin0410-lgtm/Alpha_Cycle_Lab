# SK hynix 2026Q3 outcome-blind numeric company-GP forecast

## Frozen inputs

The selected estimator was already frozen as `lagged_gp_affine_ols` after the exact
20-period chronological evaluation. The 2026Q3 prospective feature vector was then locked
on 2026-08-22 before the forecast origin of 2026-08-31 23:59:59 Asia/Seoul.

The only selected predictor is `lagged_company_gross_profit`. For 2026Q3 it is bound to the
immediately preceding 2026Q2 company gross profit from OpenDART receipt
`20260814003509`, yielding `65,991,356.0` KRW million.

The frozen selected-estimator raw-unit representation is:

`company_gp = 337,637.5345664583 + 1.101554337993561 * lagged_company_gross_profit`

No model refit, coefficient change, predictor change, feature substitution, source refresh,
or target read is permitted at this stage.

## Prospective forecast

Applying the locked feature to the locked estimator gives:

- selected 2026Q3 company-GP forecast: `73,030,702.00644387` KRW million
- equivalent scale: about `73.030702` KRW trillion
- prospective persistence benchmark: `65,991,356.0` KRW million

The persistence benchmark is frozen now because it was the preregistered historical
benchmark. This permits a clean prospective comparison once the protected 2026Q3 outcome
is later released and explicitly opened for scoring.

No numeric prediction interval is emitted. No pre-outcome interval-calibration rule was
frozen, so constructing one now would be post-selection methodology drift. Historical OOS
MAE remains a report-only error scale, not a calibrated interval.

## Source-semantic cross-check

The apparently large 2026Q2 gross-profit input was checked before forecast locking rather
than rejected by intuition alone. SK hynix's official 2Q26 results announced revenue of
79.3187 trillion won and operating profit of 60.5426 trillion won. OpenDART's official
`fnlttSinglAcntAll` guide states that `thstrm_amount` for quarterly/semiannual income or
comprehensive-income statements is the three-month amount. These checks are consistent
with retaining the already locked 2026Q2 feature semantics.

Reference URLs:

- https://news.skhynix.com/en/q2-2026-business-results/
- https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020

## Protected boundary after forecast

After this artifact is locked:

- `prospective_feature_vector_frozen = true`
- `prospective_forecast_run = true`
- `numeric_forward_forecast_enabled = true`
- `2026q3_target_read = false`
- `2026q3_source_outcome_loaded = false`
- `2026q3_evaluated = false`

The next scientific action is not to tune the model. It is to wait for the protected 2026Q3
outcome, then score the immutable selected forecast and immutable persistence benchmark
without changing the research-round model.
