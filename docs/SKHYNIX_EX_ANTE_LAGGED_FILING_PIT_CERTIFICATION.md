# SK hynix ex-ante lagged filing PIT certification

## Purpose

The ex-ante forecasting foundation forbids treating a value retrieved today as if its
historical availability were automatically known. This certification is the first concrete
promotion step. It uses only lagged issuer/regulator filing facts whose receipt identity can be
verified before the frozen forecast origin.

No company-GP target is loaded or joined in this stage and no estimator is fitted.

## Frozen source-to-target mapping

The certification covers Q2 and Q3 target periods for seven historical years:

- 2017 Q1 -> Q2, Q2 -> Q3
- 2018 Q1 -> Q2, Q2 -> Q3
- 2019 Q1 -> Q2, Q2 -> Q3
- 2020 Q1 -> Q2, Q2 -> Q3
- 2023 Q1 -> Q2, Q2 -> Q3
- 2024 Q1 -> Q2, Q2 -> Q3
- 2025 Q1 -> Q2, Q2 -> Q3

This produces 14 target rows if every source layer certifies. Q1 targets are intentionally
excluded because the registered historical product-revenue recovery does not support Q4 and
Q4 results are not generally available by the March 1-style Q1 forecast origin. No Q4 value is
inferred or synthesized.

## Five promoted feature families

Each target row must contain exactly five lagged features:

1. previous reported quarter company revenue, KRW million;
2. previous reported quarter company gross profit, KRW million;
3. previous reported quarter company gross margin, computed deterministically from the same
   filing revenue and gross profit;
4. previous reported quarter NAND revenue share, computed from directly reported product
   revenue and the directly reported product-table company total;
5. previous reported quarter Other revenue share, computed on the same basis.

A complete certification therefore contains 14 rows and 70 feature observations.

## Why later retrieval is allowed here

The original historical company objects deliberately remain marked as current-retrieval
calibration evidence rather than PIT backtest evidence. This certification does not mutate
those flags.

Instead, it separately proves the information state of an immutable filing:

- the selected company accounts share one exact OpenDART receipt number;
- the product source uses the same receipt number;
- the receipt date is no later than the target period's frozen forecast origin;
- the preserved company raw JSON file is re-read and its canonical content is tied back to the
  parsed observation;
- the actual preserved JSON file bytes receive a separate SHA-256 identity;
- the product ZIP archive bytes are re-read and must match the already certified archive
  SHA-256;
- company Revenue - Cost of Sales = Gross Profit was already required by the source parser;
- DRAM + NAND + Other = product-table total and the product total ties to consolidated company
  revenue within the frozen KRW 1 million tolerance.

The derived PIT bundle therefore represents facts from a timestamped immutable filing, not a
claim that a mutable API response retrieved today is a historical vintage.

## Timing

Source availability is conservatively represented as 23:59:59 Asia/Seoul on the filing receipt
date. A filing passes only if that timestamp is no later than the target period's frozen
forecast origin.

Under the ex-ante protocol, Q2 origin is May 31 and Q3 origin is August 31 for the relevant
calendar year. A receipt after those boundaries fails closed.

## Historical source paths

For 2017-2020, the certification reuses the already source-closed second/third-wave OpenDART
artifacts. Legacy product tables may be represented by the narrow recovery path, but the
original ZIP archive is re-hashed again here. If a direct historical product certification is
present instead, the direct certification pointer is accepted after its own verifier succeeds.

For 2023-2025, the certification uses the existing quarterly company-profitability evidence and
historical product-revenue panel. Modern product rows must retain source-vintage certification,
archived source bytes, and exact receipt binding.

## Completion gate

The certification passes only when all of the following are true:

- all 14 frozen target rows are present;
- each row has exactly the five frozen lagged filing features;
- all 70 observations pass the target-blind PIT audit;
- zero observations are rejected;
- no target values are included.

A pass still does **not** permit model fitting. The output remains a locked feature snapshot
with `target_join_allowed=false`, `estimator_fit_allowed=false`, and
`first_pit_backtest_run=false`.

## What comes next

After a successful 14-row/70-observation replay, the next scientific step is to freeze a
low-dimensional ex-ante estimator candidate set and chronological selection rule **before**
joining the historical GP targets or seeing any backtest performance. Macro, cycle-driver,
issuer-language, and memory-price features remain separate future source-certification work and
must not be backfilled into this frozen five-feature bundle after performance is observed.
