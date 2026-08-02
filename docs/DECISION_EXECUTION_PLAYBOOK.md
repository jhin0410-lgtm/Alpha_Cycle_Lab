# Decision execution playbook

The decision snapshot now converts the existing scorecard into a deterministic execution and monitoring playbook.

## Outputs

Each company receives the following fields in `scorecards.csv` and `decision_records.csv`:

- `action_readiness`
- `review_priority`
- `known_catalysts`
- `entry_conditions`
- `add_conditions`
- `reduce_conditions`
- `exit_conditions`
- `monitor_0_3m`
- `monitor_3_6m`
- `monitor_6_12m`
- `evidence_gaps`
- `playbook_basis`

The same information is appended to `report.md` under `실행 플레이북`.

## Evidence boundary

The playbook uses only the current decision snapshot:

- financial KPIs and changes
- classified OpenDART disclosures
- market trend and relative-strength features
- macro-fit and valuation status already present in the scorecard

It does not infer exact future filing dates, produce target prices, manufacture consensus estimates, or submit orders. A disclosed contract or investment becomes a monitoring item; it is not treated as confirmed future revenue or profit.

## Interpretation

`action_readiness` is a workflow state rather than a trade command.

- `position_review_ready`: positive setup, timing confirmation, and usable valuation evidence
- `conditional_without_complete_valuation`: positive setup and timing, but valuation evidence remains incomplete
- `wait_for_timing_confirmation`: positive fundamentals without sufficient price confirmation
- `watchlist_selective`: mixed setup requiring additional confirmation
- `avoid_or_reduce_review`: negative setup requiring avoidance or position-reduction review
- `research_gap`: evidence coverage is insufficient

All entry, add, reduce, and exit items are explicit conditions for human review. They do not bypass the repository's read-only and order-disabled boundaries.
