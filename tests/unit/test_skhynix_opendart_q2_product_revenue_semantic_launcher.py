from __future__ import annotations

from pathlib import Path


def test_windows_launcher_routes_through_semantic_replay_bootstrap() -> None:
    script = Path("scripts/report_skhynix_opendart_q2_product_revenue_certification.ps1")
    text = script.read_text(encoding="utf-8")

    assert "alpha_cycle.sk_hynix_opendart_q2_product_revenue_semantic_cli" in text
    assert (
        "Structural replay certifies one current consolidated product header and unit"
        in text
    )
    assert "alpha_cycle.sk_hynix_opendart_q2_product_revenue_certification_cli" not in text
