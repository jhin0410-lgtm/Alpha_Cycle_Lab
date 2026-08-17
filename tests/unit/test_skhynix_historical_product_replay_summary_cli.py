from __future__ import annotations

from datetime import UTC, date, datetime

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
    HistoricalProductRevenueFailureDiagnosticInventory,
)
from alpha_cycle.intelligence.sk_hynix_historical_product_failure_replay import (
    HistoricalProductRevenueFailureReplay,
)
from alpha_cycle.sk_hynix_opendart_historical_product_revenue_diagnostics_cli import (
    _parser,
    _summary_payload,
)


def _diagnostic(period_id: str, *, complete: bool) -> HistoricalProductRevenueFailureDiagnostic:
    return HistoricalProductRevenueFailureDiagnostic(
        period_id=period_id,
        diagnostic_path=f"{period_id}/diagnostic.json",
        rcept_no="20240516001638",
        report_name="분기보고서 (2024.03)",
        archive_path=f"{period_id}/opendart_document.zip",
        archive_sha256="a" * 64,
        normalized_text_path=f"{period_id}/normalized_document.txt",
        text_sha256="b" * 64,
        error_type="ValueError",
        error="parser failure",
        receipt_date=date(2024, 5, 16) if complete else None,
        source_url=(
            "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240516001638"
            if complete
            else None
        ),
        retrieved_at=(
            datetime(2024, 5, 16, 9, 30, tzinfo=UTC) if complete else None
        ),
        text_truncated=False if complete else None,
        archive_bytes=100 if complete else None,
        text_chars=200 if complete else None,
    )


def _replay(period_id: str, *, recovered: bool) -> HistoricalProductRevenueFailureReplay:
    return HistoricalProductRevenueFailureReplay(
        period_id=period_id,
        text_parse_succeeded=recovered,
        archive_parse_succeeded=recovered,
        parser_agreement=recovered,
        text_error=None if recovered else "text parser still fails",
        archive_error=None if recovered else "archive parser still fails",
        text_metrics={"dram_total": 1.0} if recovered else None,
        archive_metrics={"dram_total": 1.0} if recovered else None,
        replay_recoverable=recovered,
    )


def test_summary_only_flag_is_available() -> None:
    args = _parser().parse_args(
        ["--evaluation-date", "2026-08-16", "--summary-only"]
    )
    assert args.summary_only is True


def test_summary_payload_separates_recovery_and_retrieval_provenance() -> None:
    inventory = HistoricalProductRevenueFailureDiagnosticInventory(
        failed_periods=("2024Q1", "2025Q1"),
        diagnostics=(
            _diagnostic("2024Q1", complete=False),
            _diagnostic("2025Q1", complete=True),
        ),
        invalid_diagnostics=(),
        missing_diagnostic_periods=(),
        diagnostic_bundle_coverage_complete=True,
        diagnostic_bundle_integrity_complete=True,
    )
    payload = _summary_payload(
        evaluation_date=date(2026, 8, 16),
        failed_periods=("2024Q1", "2025Q1"),
        inventory=inventory,
        replays=[
            _replay("2024Q1", recovered=True),
            _replay("2025Q1", recovered=False),
        ],
    )

    assert payload["replay_recoverable_periods"] == ("2024Q1",)
    assert payload["replay_unresolved_periods"] == ("2025Q1",)
    assert payload["retrieval_provenance_complete_periods"] == ("2025Q1",)
    assert payload["retrieval_provenance_incomplete_periods"] == ("2024Q1",)
    assert payload["network_requested"] is False
    assert payload["source_fact_promoted"] is False
    assert payload["certification_created"] is False
