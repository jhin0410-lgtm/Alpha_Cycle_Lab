# Partial valuation coverage in decision snapshots

The decision layer treats the research company universe as authoritative.

- A valuation snapshot may omit a decision company when issued-share evidence is unavailable.
- The missing company is retained with `valuation_status=valuation_not_available`.
- Market capitalization, valuation multiples, yields, and valuation score remain unavailable.
- Other evidence such as financial KPIs, disclosures, macro regime, and market timing remains usable.
- A valuation snapshot containing a company outside the decision universe still fails closed.

This behavior prevents incomplete OpenDART share-count evidence from aborting an otherwise valid decision report without manufacturing valuation data.
