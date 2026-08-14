from __future__ import annotations

from alpha_cycle.intelligence.sector_vertical_registry import (
    SECTOR_VERTICALS,
    get_sector_vertical,
)


def test_sector_registry_declares_distinct_industry_specific_contracts() -> None:
    expected = {
        "semiconductor",
        "defense",
        "shipbuilding",
        "power_equipment",
        "nuclear",
        "construction",
        "battery",
        "auto",
        "bio",
        "internet_platform",
        "robotics",
    }
    assert set(SECTOR_VERTICALS) == expected
    assert all(definition.decision_score_enabled is False for definition in SECTOR_VERTICALS.values())

    assert "memory_pricing" in get_sector_vertical("semiconductor").requirement_keys
    assert "export_pipeline" in get_sector_vertical("defense").requirement_keys
    assert "newbuild_price" in get_sector_vertical("shipbuilding").requirement_keys
    assert "lead_time" in get_sector_vertical("power-equipment").requirement_keys
    assert "licensing" in get_sector_vertical("nuclear").requirement_keys
    assert "pf_exposure" in get_sector_vertical("construction").requirement_keys
    assert "metal_prices" in get_sector_vertical("battery").requirement_keys
    assert "inventory_incentives" in get_sector_vertical("auto").requirement_keys
    assert "clinical_readout" in get_sector_vertical("bio").requirement_keys
    assert "take_rate_arpu" in get_sector_vertical("internet-platform").requirement_keys
    assert "component_supply" in get_sector_vertical("robotics").requirement_keys


def test_sector_contracts_do_not_collapse_to_one_generic_factor_template() -> None:
    requirement_sets = {
        sector_id: set(definition.requirement_keys)
        for sector_id, definition in SECTOR_VERTICALS.items()
    }
    assert requirement_sets["semiconductor"] != requirement_sets["defense"]
    assert requirement_sets["defense"] != requirement_sets["shipbuilding"]
    assert requirement_sets["construction"] != requirement_sets["bio"]
    assert requirement_sets["battery"] != requirement_sets["internet_platform"]

    unique_union = set().union(*requirement_sets.values())
    common = set.intersection(*requirement_sets.values())
    assert len(unique_union) > 50
    assert len(common) < 5
