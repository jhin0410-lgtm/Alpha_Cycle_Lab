from __future__ import annotations

from pathlib import Path

import pytest

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    load_official_ir_document_registry,
)


def test_identity_anchor_mapping_is_rejected_instead_of_stringified(tmp_path: Path) -> None:
    registry = tmp_path / "bad-registry.yaml"
    registry.write_text(
        """schema_version: 1
issuers:
  \"005930\":
    issuer_name: Samsung Electronics
    documents:
      bad:
        source_id: samsung_ir
        document_role: earnings_presentation
        content_type: pdf
        source_url: https://example.com/a.pdf
        source_published_date: 2026-07-30
        period_start: 2026-04-01
        period_end: 2026-06-30
        parser_id: parser_v1
        expected_page_count: 1
        required_identity_anchors:
          - Appendix 2: Results by Business Segment
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="entries must be strings"):
        load_official_ir_document_registry(registry)
