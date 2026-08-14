from __future__ import annotations

from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    DEFAULT_IR_DOCUMENT_REGISTRY,
    load_official_ir_document_registry,
)
from alpha_cycle.intelligence.official_semiconductor_ir_refresh import (
    build_official_ir_refresh_plan,
)
from alpha_cycle.official_semiconductor_ir_refresh_cli import (
    refresh_official_semiconductor_ir,
)


def test_official_ir_refresh_dependency_chain_is_present() -> None:
    assert Path(DEFAULT_IR_DOCUMENT_REGISTRY).is_file()
    specs = load_official_ir_document_registry(DEFAULT_IR_DOCUMENT_REGISTRY)
    assert "samsung_005930_2026q2_earnings" in specs
    assert callable(refresh_official_semiconductor_ir)


def test_refresh_plan_keeps_unregistered_hynix_explicit() -> None:
    plan = build_official_ir_refresh_plan(
        evaluation_date=date(2026, 8, 14),
        registry_path=DEFAULT_IR_DOCUMENT_REGISTRY,
    )
    by_ticker = {item.ticker: item for item in plan.issuers}
    assert by_ticker["005930"].selected_document_id == "samsung_005930_2026q2_earnings"
    assert by_ticker["000660"].selected_document_id is None
    assert by_ticker["000660"].status == "unresolved_no_registered_document"
