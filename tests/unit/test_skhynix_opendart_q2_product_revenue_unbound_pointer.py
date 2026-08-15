from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)


def test_verifier_rejects_naked_certification_pointer_without_bound_parser_contract(
    tmp_path: Path,
) -> None:
    pointer = tmp_path / "latest_certification.json"
    pointer.write_text(
        json.dumps(
            {
                "status": "skhynix_opendart_q2_product_revenue_certified",
                "evaluation_date": "2026-08-14",
                "evidence_id": "a" * 64,
                "parser_contract_bound": False,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="parser contract is not bound"):
        load_periodic_product_revenue_certification(
            pointer,
            evaluation_date=date(2026, 8, 14),
        )
