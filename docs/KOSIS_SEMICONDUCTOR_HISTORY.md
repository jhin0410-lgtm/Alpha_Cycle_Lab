# KOSIS Semiconductor History Diagnostics

This layer captures official KOSIS monthly semiconductor activity indexes after the source identities have been live-verified.

## Verified source bindings

### Production / shipment / inventory

- organization: `101`
- table: `DT_1F02001`
- table name: `시도/산업별 광공업생산지수(2020=100)`
- classification: `00 / C261` = `전국 / 반도체 제조업`
- items:
  - `T10` production index, original
  - `T11` producer shipment index, original
  - `T12` producer inventory index, original
  - `T20` production index, seasonally adjusted
  - `T21` producer shipment index, seasonally adjusted
  - `T22` producer inventory index, seasonally adjusted

### Capacity / utilization

- organization: `101`
- table: `DT_1F32001`
- table name: `제조업 생산능력 및 가동률지수(2020=100)`
- classification: `C261` = `반도체 제조업`
- items:
  - `T10` production-capacity index
  - `T20` utilization index, original
  - `T30` utilization index, seasonally adjusted

These bindings were verified against the live KOSIS service on 2026-08-09 before this history layer was added.

## Capture policy

`alpha-cycle-kosis-semiconductor-history` re-verifies both table identities on every run and then requests each verified series separately. The default window is the latest 180 monthly observations. Requests remain far below KOSIS per-request cell limits and make source provenance explicit per series.

Artifacts preserve:

- raw search responses
- raw table metadata responses
- one raw parameter response per metric
- normalized series rows
- per-series source-change dates (`LST_CHN_DE`)
- SHA-256 hashes for raw, normalized, and diagnostic payloads
- derived diagnostics
- an ASCII-safe latest pointer for Windows PowerShell compatibility

## Derived diagnostics

Original indexes are used for 12-month percentage changes:

- production YoY
- shipment YoY
- inventory YoY
- production-capacity YoY
- utilization YoY

Seasonally adjusted indexes are used for 1-month percentage changes:

- production MoM
- shipment MoM
- inventory MoM
- utilization MoM

Additional transparent diagnostics include:

- shipment YoY minus inventory YoY
- production YoY minus shipment YoY
- inventory-index / shipment-index ratio
- positive short-term momentum confirmations
- a simple shipment/inventory sign-and-spread phase label

The inventory/shipment ratio is a ratio between two `2020=100` indexes. It is **not** a physical stock-to-sales ratio and must not be described as one.

## Heuristic phase labels

The phase label is intentionally simple and auditable:

- shipments non-negative YoY + inventory negative YoY → `recovery_destocking`
- shipments and inventory non-negative, shipments growing faster → `expansion_inventory_controlled`
- shipments and inventory non-negative, inventory growing at least as fast → `expansion_inventory_build`
- shipments and inventory both negative → `contraction_destocking`
- shipments negative + inventory non-negative → `demand_slowdown_inventory_build`

This is a diagnostic description, not a validated economic regime model.

## Trust boundary

Every artifact remains:

- `revision_sensitive = true`
- `historical_vintage_certified = false`
- `point_in_time_backtest_eligible = false`
- `heuristic_phase_certified = false`
- `industry_cycle_certified = false`
- `decision_score_enabled = false`

KOSIS can revise historical observations. A current history snapshot must therefore not be treated as the exact information set that was available at an earlier historical date. This layer is suitable for current research diagnostics and methodology development, but not yet for point-in-time backtest claims or automated investment scoring.

## CLI

```powershell
python -m alpha_cycle.kosis_semiconductor_history_cli
```

Optional history window:

```powershell
python -m alpha_cycle.kosis_semiconductor_history_cli --months 240
```

The CLI requires `KOSIS_API_KEY` in the local environment. The key is never written into artifacts.
