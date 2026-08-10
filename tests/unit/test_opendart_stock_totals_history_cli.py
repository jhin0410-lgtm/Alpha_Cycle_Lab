from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.opendart_stock_totals_history_cli import (
    collect_stock_totals_history,
    write_stock_totals_history,
)
from alpha_cycle.providers.opendart import CorpCode
from alpha_cycle.providers.opendart_valuation import StockTotalsBatch

RESEARCH_ID = "a" * 64


def _research_snapshot(root: Path) -> Path:
    directory = root / "research"
    directory.mkdir()
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": RESEARCH_ID,
                "evaluation_date": "2026-08-10",
            }
        ),
        encoding="utf-8",
    )
    (directory / "raw_opendart.json").write_text(
        json.dumps(
            {
                "005930": {
                    "corp": {
                        "corp_code": "00126380",
                        "corp_name": "삼성전자",
                        "stock_code": "005930",
                        "modify_date": "2026-01-01",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return directory


def _row(
    *,
    year: int,
    report_code: str,
    period_end: str,
    available_date: str,
    issued_shares: int,
) -> dict[str, object]:
    return {
        "ticker": "005930",
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "business_year": year,
        "report_code": report_code,
        "period_end": date.fromisoformat(period_end),
        "available_date": date.fromisoformat(available_date),
        "receipt_no": available_date.replace("-", "") + "000001",
        "security_name": "보통주",
        "security_class": "common",
        "issued_shares": issued_shares,
    }


class StubClient:
    def stock_totals(
        self,
        corp: CorpCode,
        *,
        business_year: int,
        report_code: str,
    ) -> StockTotalsBatch:
        assert corp.stock_code == "005930"
        rows: list[dict[str, object]] = []
        if (business_year, report_code) == (2025, "11011"):
            rows.append(
                _row(
                    year=2025,
                    report_code="11011",
                    period_end="2025-12-31",
                    available_date="2026-03-10",
                    issued_shares=5_900_000_000,
                )
            )
        if (business_year, report_code) == (2026, "11013"):
            rows.append(
                _row(
                    year=2026,
                    report_code="11013",
                    period_end="2026-03-31",
                    available_date="2026-05-15",
                    issued_shares=5_880_000_000,
                )
            )
        if (business_year, report_code) == (2026, "11012"):
            rows.append(
                _row(
                    year=2026,
                    report_code="11012",
                    period_end="2026-06-30",
                    available_date="2026-08-14",
                    issued_shares=5_870_000_000,
                )
            )
        frame = pd.DataFrame(rows)
        return StockTotalsBatch(
            frame=frame,
            raw_payload={
                "status": "000" if rows else "013",
                "year": business_year,
                "report_code": report_code,
            },
            corp=corp,
        )


def test_history_keeps_only_share_counts_available_by_evaluation_date(tmp_path: Path) -> None:
    snapshot = collect_stock_totals_history(
        _research_snapshot(tmp_path),
        StubClient(),
        history_years=2,
        now=datetime(2026, 8, 10, 7, 0, tzinfo=UTC),
    )

    assert snapshot.research_snapshot_id == RESEARCH_ID
    assert snapshot.evaluation_date == date(2026, 8, 10)
    assert len(snapshot.frame) == 2
    assert set(snapshot.frame["report_code"].astype(str)) == {"11011", "11013"}
    assert snapshot.frame["available_date"].max() == date(2026, 5, 15)
    assert snapshot.payload_without_id()["availability_date_bound"] is True
    assert snapshot.payload_without_id()["historical_vintage_certified"] is False
    assert snapshot.payload_without_id()["point_in_time_backtest_eligible"] is False
    assert snapshot.payload_without_id()["decision_score_enabled"] is False


def test_history_writer_is_immutable_and_non_scoring(tmp_path: Path) -> None:
    snapshot = collect_stock_totals_history(
        _research_snapshot(tmp_path),
        StubClient(),
        history_years=2,
        now=datetime(2026, 8, 10, 7, 0, 0, 123456, tzinfo=UTC),
    )
    output = tmp_path / "output"

    pointer = write_stock_totals_history(output, snapshot)

    assert pointer["status"] == "stock_totals_history_captured"
    assert pointer["row_count"] == 2
    assert pointer["decision_score_enabled"] is False
    assert pointer["point_in_time_backtest_eligible"] is False
    assert pointer["account_api_enabled"] is False
    assert pointer["order_api_enabled"] is False
    artifact = Path(str(pointer["artifact_directory"]))
    assert (artifact / "stock_totals_history.csv").is_file()
    assert (artifact / "raw_periods.json").is_file()
    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["research_snapshot_id"] == RESEARCH_ID
    assert manifest["availability_date_bound"] is True
    assert manifest["historical_vintage_certified"] is False

    try:
        write_stock_totals_history(output, snapshot)
    except FileExistsError:
        pass
    else:
        raise AssertionError("identical immutable history artifact must not be overwritten")
