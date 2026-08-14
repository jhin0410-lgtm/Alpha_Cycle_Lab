from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_official_ir_board_api_capture import BoardRowSummary
from alpha_cycle.sk_hynix_official_ir_board_api_capture_cli import _row_summary


def test_board_cli_row_summary_preserves_source_fields() -> None:
    row = BoardRowSummary(
        seq="9001",
        title="2026년 2분기 실적발표",
        display_date="2026.07.29",
        file_url1="/call.mp3",
        file_url2="/earnings.pdf",
        file_url3="/press.pdf",
        file_url4="/ceo.pdf",
        candidate_2026q2=True,
    )

    assert _row_summary(row) == {
        "seq": "9001",
        "title": "2026년 2분기 실적발표",
        "display_date": "2026.07.29",
        "file_url1": "/call.mp3",
        "file_url2": "/earnings.pdf",
        "file_url3": "/press.pdf",
        "file_url4": "/ceo.pdf",
        "candidate_2026q2": True,
    }
