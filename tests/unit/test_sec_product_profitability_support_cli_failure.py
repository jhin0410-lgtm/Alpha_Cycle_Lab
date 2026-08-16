from __future__ import annotations

from pathlib import Path

import pytest

from alpha_cycle.sec_product_profitability_support_cli import main


def test_cli_surfaces_preserved_raw_diagnostic_path(monkeypatch, tmp_path) -> None:
    import alpha_cycle.sec_product_profitability_support_cli as module

    document_id = "skhynix_000660_2026_sec_424b4_product_profitability_support"
    spec = object()
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "AlphaCycleLab test@example.com")
    monkeypatch.setattr(
        module,
        "load_sec_product_profitability_registry",
        lambda path: {document_id: spec},
    )

    def fail_capture(*args, **kwargs):
        raise ValueError("SEC product-profitability row must resolve five periods: nand count=0")

    diagnostic = tmp_path / "failed" / "bundle" / "diagnostic.json"
    monkeypatch.setattr(module, "capture_sec_product_profitability_support", fail_capture)
    monkeypatch.setattr(
        module,
        "preserve_sec_product_profitability_failure",
        lambda *args, **kwargs: diagnostic,
    )

    with pytest.raises(RuntimeError) as exc_info:
        main(
            [
                "--document-id",
                document_id,
                "--observed-date",
                "2026-08-16",
                "--output",
                str(tmp_path),
            ]
        )
    message = str(exc_info.value)
    assert "nand count=0" in message
    assert f"raw diagnostic preserved at {diagnostic}" in message


def test_cli_retains_original_failure_when_diagnostic_capture_also_fails(
    monkeypatch, tmp_path
) -> None:
    import alpha_cycle.sec_product_profitability_support_cli as module

    document_id = "skhynix_000660_2026_sec_424b4_product_profitability_support"
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "AlphaCycleLab test@example.com")
    monkeypatch.setattr(
        module,
        "load_sec_product_profitability_registry",
        lambda path: {document_id: object()},
    )
    monkeypatch.setattr(
        module,
        "capture_sec_product_profitability_support",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("parser failed")),
    )
    monkeypatch.setattr(
        module,
        "preserve_sec_product_profitability_failure",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(RuntimeError) as exc_info:
        main(
            [
                "--document-id",
                document_id,
                "--observed-date",
                "2026-08-16",
                "--output",
                str(Path(tmp_path)),
            ]
        )
    message = str(exc_info.value)
    assert "capture=parser failed" in message
    assert "diagnostic=disk full" in message
