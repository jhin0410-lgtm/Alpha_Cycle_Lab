from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.official_semiconductor_ir_collector_cli import capture_official_ir_document


def test_capture_rejects_secondary_sk_hynix_url_before_reading_local_pdf(tmp_path: Path) -> None:
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """
schema_version: 1
issuers:
  "000660":
    issuer_name: SK hynix
    documents:
      skhynix_2026q2_secondary_copy:
        source_id: sk_hynix_ir
        document_role: earnings_presentation
        content_type: pdf
        source_url: https://example.com/2Q26_SKH_Earnings.pdf
        source_published_date: 2026-07-29
        period_start: 2026-04-01
        period_end: 2026-06-30
        parser_id: sk_hynix_earnings_presentation_2026q2_v1
        expected_page_count: 19
        required_identity_anchors:
          - "2026.07.29 | Investor Relations"
""".strip(),
        encoding="utf-8",
    )
    # If source policy is checked too late, capture would reach this missing local path
    # and raise a different error. The issuer-domain error must win first.
    missing_local_pdf = tmp_path / "never-read.pdf"

    with pytest.raises(ValueError, match="issuer site or its registered official CDN"):
        capture_official_ir_document(
            "skhynix_2026q2_secondary_copy",
            evaluation_date=date(2026, 8, 14),
            registry_path=registry,
            output=tmp_path / "out",
            local_document=missing_local_pdf,
        )
