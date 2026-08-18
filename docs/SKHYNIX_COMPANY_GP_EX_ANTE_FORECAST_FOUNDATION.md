# SK hynix company-GP ex-ante forecasting foundation

## Why this layer exists

V5 established a development-stage empirical relationship between same-quarter company gross
profit and same-quarter cycle/mix variables. That is useful evidence, but it is not a
pre-earnings forecast because several V5 inputs are only known with or around the earnings
outcome.

The ex-ante layer therefore starts a separate scientific track. Its target is still SK hynix
company gross profit, but every feature must be provably available before a deterministic
forecast origin.

## Frozen forecast origin

Protocol v1 uses `quarter_end_minus_30_calendar_days` at 23:59:59 Asia/Seoul. It does not use
the eventual earnings-release date to define the cutoff because that would make historical
origins depend on future event knowledge.

For the protected current research periods:

- 2026Q3 origin: 2026-08-31 23:59:59 Asia/Seoul
- 2026Q4 fallback origin: 2026-12-01 23:59:59 Asia/Seoul

2026Q3 remains a protected target under the separately frozen V5 holdout protocol. It may also
serve as an ex-ante prospective outcome only if an ex-ante forecast is locked before the origin
without reading the Q3 target or current-quarter earnings actuals. If that origin is missed,
2026Q4 becomes the fallback prospective ex-ante candidate.

## Point-in-time rule

A historical value being visible through an API today does not prove that the same value was
available at the historical forecast origin.

The feature frontier distinguishes four provenance classes:

1. `timestamped_immutable_filing`: a pinned issuer/regulator filing or publication whose
   historical identity can be verified even when downloaded later.
2. `historical_version_archive`: an official historical version of a revision-prone series.
3. `prospective_snapshot`: exact source bytes captured and SHA-256 bound before the origin.
4. `current_retrieval_only`: a current download of an old observation without historical
   version identity. This class is never historical PIT fit evidence.

The existing OpenDART company-profitability calibration panel explicitly states that it is not
PIT backtest evidence because it was queried at the current date. The existing ECOS adapter
conservatively sets `available_date` to the retrieval date. KOSIS is also treated as
revision-prone until row identity/version timing is separately certified. This foundation does
not silently upgrade any of those sources.

## Frozen feature frontier

The first frontier registers candidate families but marks every historical feature as not yet
PIT fit-eligible:

- lagged company revenue, gross profit, and gross margin;
- lagged NAND/Other revenue mix;
- lagged DRAM/NAND ASP and bit-volume direction regimes;
- partial-quarter USD/KRW from official ECOS;
- KOSIS semiconductor production/shipment/inventory/export state;
- issuer prior-quarter outlook language;
- a memory-price proxy gap, which remains unresolved and cannot be captured or fitted.

Current-quarter company GP, company revenue, product revenue, and current-quarter realized ASP
or bit-shipment directions are explicitly forbidden as ex-ante features.

## Historical evaluation frozen before backtest

The protocol requires chronological expanding-window evaluation. Random cross-validation is
forbidden. The primary metric is MAE in KRW million, and a candidate must strictly beat the
previous-reported-quarter gross-profit persistence benchmark.

The protocol freezes only the evaluation design and feature frontier. It does **not** freeze a
final feature set or estimator. No estimator may be fitted until PIT source certification has
produced enough eligible development rows and a separate model-specific rank/DOF contract is
frozen.

The minimum 12 complete development rows is only a heuristic floor, not a statistical theorem.
Any eventual parametric model still needs its own parameter-count, rank, residual-DOF, and
chronological-fold gates.

## Prospective capture ledger

`sk_hynix_company_gp_ex_ante_capture.py` provides an append-only private source-byte ledger.
For revision-prone sources, a future provider adapter can pass the exact raw response bytes to
this layer. The module:

- timestamps the capture from the runtime clock;
- SHA-256 archives the exact bytes;
- records source availability and the frozen-period origin;
- hash-chains every receipt;
- rejects modified archived bytes on replay;
- marks a capture eligible only when both source availability and capture occurred by the
  frozen origin;
- never reads a target.

This is the mechanism intended for prospective ECOS/KOSIS capture before a future forecast
origin.

## What this PR does not claim

This foundation does not claim that an ex-ante SK hynix GP model exists yet. It does not run a
historical PIT backtest, select a model, predict 2026Q3 GP, value SK hynix, generate a target
price, or create an investment decision score.

The next scientific step is source certification:

1. certify lagged immutable issuer/regulator filing facts using pinned receipt/publication
   identities and source-byte hashes;
2. pin the exact ECOS USD/KRW series identity and KOSIS semiconductor classifications;
3. begin prospective source-byte capture before the protected origin;
4. build target-blind PIT feature rows;
5. only then freeze a model-specific feature set and estimator before any prospective forecast.
