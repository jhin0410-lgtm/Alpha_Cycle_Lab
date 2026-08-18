# SK hynix ex-ante PIT panel expansion

## Purpose

This stage expands the target-blind lagged-filing feature panel from 14 target quarters
(70 feature observations) to the 20 target quarters required by the frozen estimator
sample gate. It does **not** read historical gross-profit targets, fit an estimator, run a
backtest, or open the protected 2026Q3 outcome.

The expansion manifest was committed before source replay. A second pre-replay freeze
clarified one deterministic acquisition detail: product filing discovery always uses the
calendar interval from the day after source-quarter end through source-quarter end + 120
days. The exact periodic filing name is required and correction disclosures remain excluded.
No year-specific discovery-window tuning is allowed after source replay.

## Frozen row selection

Four rows are fixed and cannot be replaced by better-performing alternatives:

- 2021Q1 filing -> 2021Q2 feature row
- 2021Q2 filing -> 2021Q3 feature row
- 2022Q1 filing -> 2022Q2 feature row
- 2022Q2 filing -> 2022Q3 feature row

Two more rows must come from one complete legacy year. The source-only priority is frozen as:

1. 2016 Q1/Q2 filings -> 2016Q2/Q3 feature rows
2. if and only if that pair is incomplete, 2015 Q1/Q2 -> 2015Q2/Q3
3. if and only if that pair is incomplete, 2014 Q1/Q2 -> 2014Q2/Q3

A partial legacy year is never accepted. Target values, benchmark errors, model scores, and
backtest results are unavailable to the selector.

## Source contract

Every added row requires an immutable OpenDART filing identity and preserved source bytes.
The company all-accounts payload must provide direct Revenue, Cost of Sales, and Gross Profit
facts from one receipt, and `Revenue - Cost of Sales = Gross Profit` must reconcile exactly.
The product filing must parse direct DRAM, NAND, Other, and Total rows under the existing
certified parser contract. Synthetic allocation and residual `Other` construction are
forbidden.

Company and product receipts must match exactly. For the four 2021-2022 source periods the
manifest also pins the already-known receipt number before replay. For legacy years the
receipt is discovered from the exact filing and then bound by its immutable receipt number
and archived source bytes. The receipt must be available no later than the target quarter's
frozen `quarter_end - 30 calendar days, 23:59:59 Asia/Seoul` forecast origin.

The preserved company JSON bytes and product ZIP bytes are SHA-256 verified. Product total
revenue must reconcile to company revenue within KRW 1 million. The five features are then
derived under the unchanged lagged-filing semantics:

- `lagged_company_revenue`
- `lagged_company_gross_profit`
- `lagged_company_gross_margin`
- `lagged_nand_revenue_share`
- `lagged_other_revenue_share`

## Why the existing PIT audit is not used to fake acceptance

The original ex-ante protocol registered only the earlier 14 development rows. Its generic
PIT audit therefore rejects 2021-2022 and legacy target periods as unsupported even when a
new filing is temporally valid. This expansion does not weaken or bypass that historical
contract. Instead it applies the same feature provenance and forecast-origin timing rules in
a source-only expansion audit.

Once a local replay identifies the first complete legacy year and produces exactly 20 rows /
100 observations, the next required step is a separate **target-blind period-scope refreeze**
that names the exact 20 target periods. Only after that refreeze may a first historical target
join or estimator fit be considered.

## Completion gate

Success requires all of the following:

- the bound base bundle remains exactly 14 rows / 70 observations;
- all four fixed 2021-2022 source rows pass;
- exactly one complete legacy pair is selected by the frozen source-only priority;
- exactly six rows / 30 observations are added;
- the composed panel has exactly 20 rows / 100 observations;
- every added observation is PIT-eligible under immutable-filing provenance and forecast
  timing;
- rejected added observations = 0;
- no duplicate target-period/feature key exists;
- target values remain absent.

Only a complete panel is persisted as the new combined bundle. An incomplete run writes
private diagnostics but does not promote a partial combined bundle.

## Trust boundary after success

Even after the expansion gate passes:

- historical target join: **false**
- estimator fit: **false**
- historical backtest: **false**
- final estimator selection: **false**
- 2026Q3 target read: **false**
- 2026Q3 current-quarter outcome load: **false**
- forward forecast / fair value / target price / decision score: **false**

The only newly opened action is the exact target-blind period-scope refreeze.
