# Alpha Cycle sector vertical roadmap

## Purpose

Alpha Cycle is not intended to become a generic factor screener that applies the same
weights to every industry.  The common architecture should carry a thesis from macro
and liquidity through industry economics, company earnings, expectations, valuation,
catalysts, market confirmation, scenarios, and position choice.  The variables inside
that chain are industry-specific.

The code contract lives in `sector_vertical.py` and the industry declarations live in
`sector_vertical_registry.py`.  Missing evidence is a research gap, not a zero score.

## Maturity gates

A vertical advances through these gates.  The gates are evidence-readiness states, not
investment ratings.

1. **Contract declared** — the sector-specific questions and preferred source types are explicit.
2. **Industry economics connected** — demand, supply, pricing, inventory/capacity, policy, and sector-specific bottlenecks have source-bounded evidence.
3. **Company transmission connected** — the industry variables are mapped into company mix, volume, ASP, margin, cash flow, and balance-sheet consequences.
4. **Expectation gap connected** — certified forward expectations/revisions exist and can be compared with the internal operating view.
5. **Catalyst timing connected** — 1/3/6/12-month events, prerequisites, surprise potential, and failure conditions are explicit.
6. **Valuation/scenario connected** — current expectations are translated into non-spurious Bull/Base/Bear earnings and valuation ranges with invalidation conditions.
7. **Cross-sectional eligibility** — only after the prior gates are sufficiently covered may the sector participate in a comparable ranking or portfolio opportunity-cost engine.

No gate is passed by inventing a proxy whose semantics are not certified.

## Semiconductor vertical

### Already connected

- KOSIS production, shipment, inventory, capacity, and utilization diagnostics.
- OpenDART multi-period financials and issuer earnings/margin transmission.
- Kiwoom/Toss/KRX-bounded price evidence and lagged investor-flow context.
- Current P/B on latest observable book equity.
- Own-history P/B distribution and descriptive P/B-versus-TTM-ROE context.
- OpenDART disclosure/catalyst evidence.
- KIS raw estimate-perform structure with an explicit fail-closed consensus/revision boundary.

### Highest-value missing evidence

1. DRAM/NAND contract or otherwise defensible memory-price history.
2. HBM demand, generation mix, ASP/mix, capacity allocation, yield, packaging bottlenecks, and customer qualification.
3. Server/AI/PC/mobile end-demand decomposition instead of aggregate shipment only.
4. Global supplier wafer/CAPEX and supply-addition schedule, not only Korean aggregate capacity plus issuer CAPEX.
5. Company competitive-position evidence: qualification, technology node, HBM share/mix, foundry/NAND/mobile drag where applicable.
6. Certified consensus/revision data with documented period and aggregation semantics.
7. Global liquidity/US real-rate/DXY/SOX/foreign-flow evidence linked to the semiconductor vertical.
8. Structured export-control/geopolitical primary-source evidence.
9. A forward operating bridge that converts demand/price/mix/capacity assumptions into quarterly revenue, margin, operating profit, and scenario outcomes.

The next semiconductor milestone is not another P/B tweak.  It is the **industry economics → company earnings transmission model**, followed by the expectation gap.

## Defense

Core variables: national defense budgets and procurement plans; rearmament/inventory
replenishment; export pipeline and bid stage; backlog and delivery schedule; production
capacity and bottlenecks; export-vs-domestic/product margin mix; working capital and
advance payments; FX; export licenses/diplomatic gates; earnings revisions; contract,
delivery, and test milestones; backlog-aware valuation.

Primary-source preference: defense ministries, DAPA and equivalent procurement agencies,
NATO/government budget documents, company filings and IR, export-control/licensing
agencies.

## Shipbuilding

Core variables: global order cycle; newbuild prices; orderbook and delivery slots;
yard/dock/labor capacity; steel plate/input costs; USD/KRW; LNGC/container/tanker mix;
low-price backlog burn-off versus high-price revenue recognition; advances/working
capital; earnings revisions; major orders and margin catalysts; cycle-adjusted valuation.

A shipbuilder should not inherit a defense backlog model: price, yard capacity, vessel
mix, steel, and construction timing are first-class variables.

## Power equipment

Core variables: US/global grid CAPEX; utility/project order flow; backlog/book-to-bill;
transformer/switchgear lead times; plant capacity expansion; pricing/mix; copper and
other inputs; localization/tariff policy; backlog-to-margin conversion; revisions;
capacity/ramp catalysts; ROE/backlog-aware valuation.

## Nuclear

Core variables: national capacity policy; project and SMR pipeline; licensing stages;
financing/export-credit support; EPC schedule and revenue recognition; local-content and
partner structure; cost-overrun/delay risk; award probability; preferred bidder, final
contract, licensing and construction milestones; probability-aware valuation.

Policy headlines alone are not an investable catalyst until the project gates and
revenue path are mapped.

## Construction

Core variables: rates/credit/PF conditions; housing transactions, presales and unsold
inventory; PF guarantees and contingent liabilities; domestic and overseas backlog;
materials/labor/construction costs; low-margin-site burn-off; unbilled receivables and
working capital; housing/SOC policy; revisions; presale/order/PF-resolution catalysts;
P/B/ROE/NAV-style valuation where appropriate.

The cash-conversion and PF-risk path is mandatory; revenue growth by itself is not.

## Battery

Core variables: EV registrations and penetration; OEM/cell/material inventory; plant
utilization; lithium/nickel/cobalt; cell/material ASP and mix; LFP/NCM chemistry;
customer/platform exposure; capacity/CAPEX/JVs; subsidies, tariffs and localization;
utilization/ASP-to-margin transmission; revisions; OEM launches/ramp/policy catalysts;
cycle-adjusted valuation.

## Auto

Core variables: regional volumes and share; dealer inventory and incentives; SUV/luxury/
HEV/EV mix; FX; tariffs/local-content policy; EV-transition economics; warranty and
residual-value risk; volume/mix-to-margin conversion; CAPEX/FCF and shareholder returns;
revisions; launches/policy/capital-return catalysts; P/E/P/B/FCF valuation.

## Bio

Core variables: pipeline and trial stage; endpoints/readouts; regulatory path; standard
of care and competing pipelines; patient population, pricing and penetration; payer and
reimbursement; cash burn/runway; dilution/convertibles; licensing/partner deals; rNPV
or scenario valuation; binary-event expectations and positioning.

Traditional cyclical valuation should not be forced onto pre-commercial biotech.

## Internet/platform

Core variables: users/engagement; ad market and pricing; commerce GMV; take rate/ARPU;
AI infrastructure CAPEX; AI monetization or cost savings; platform/privacy/competition
regulation; operating leverage; revisions; product/earnings/regulatory catalysts;
growth-adjusted P/E/FCF valuation.

## Robotics/automation

Core variables: customer automation CAPEX; order/backlog; unit shipments/installations;
reducer/servo/sensor/component supply; BOM and cost-down; software/service recurring
mix; customer concentration; scale-to-margin conversion; revisions; large-order/new-
product catalysts; growth/margin valuation.

## Implementation order

The implementation order is based on the user's investment process, not on ease of
coding:

1. Finish semiconductor industry-economics and company-transmission adapters.
2. Add certified expectation-gap and forward scenario interfaces.
3. Add structured catalyst horizons and scenario/invalidation outputs.
4. Generalize the completed interfaces, preserving sector-specific contracts.
5. Implement defense, shipbuilding, power-equipment, nuclear, and construction adapters.
6. Implement battery, auto, internet/platform, robotics, and bio adapters.
7. Only then enable broad cross-sectional opportunity-cost ranking.

## Ranking eligibility rule

A company may appear in discovery screens before its vertical is complete, but a deep
cross-sector investment ranking must display its vertical readiness and may not imply
comparability when required evidence is missing, blocked, or semantically uncertified.
This prevents breadth from masquerading as analytical depth.
