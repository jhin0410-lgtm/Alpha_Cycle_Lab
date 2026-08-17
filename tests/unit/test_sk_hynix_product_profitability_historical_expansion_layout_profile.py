from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_layout_profile import (
    profile_historical_expansion_failures,
)

_PERIODS = ("2021Q1", "2021Q2", "2021Q3", "2022Q1", "2022Q2", "2022Q3")


def _archive_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("REPORT.xml", "<table><tr><td>D램</td><td>1,000</td></tr></table>")
        archive.writestr("META.txt", "synthetic fixture")
    return buffer.getvalue()


def _write_failure(root: Path, period_id: str, index: int) -> None:
    directory = root / period_id / "failed" / f"20260817T08080{index}000000Z__fixture"
    directory.mkdir(parents=True)
    archive_path = directory / "opendart_document.zip"
    text_path = directory / "normalized_document.txt"
    diagnostic_path = directory / "diagnostic.json"

    archive = _archive_bytes()
    text = "\n".join(
        (
            "매출액",
            "단위 : 백만원",
            "3개월",
            "누적",
            "D램",
            "1,000",
            "낸드플래시",
            "500",
            "기타 제품",
            "100",
            "합계",
            "1,600",
        )
    )
    archive_path.write_bytes(archive)
    text_path.write_text(text, encoding="utf-8")
    payload = {
        "status": "skhynix_opendart_q2_product_revenue_parse_failed",
        "captured_at": "2026-08-17T08:08:00+00:00",
        "rcept_no": f"20210{index + 1:02d}17000667"[-14:],
        "report_name": f"fixture {period_id}",
        "receipt_date": "2021-05-17",
        "retrieved_at": "2026-08-17T08:08:00+00:00",
        "archive_path": str(archive_path),
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "archive_bytes": len(archive),
        "normalized_text_path": str(text_path),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_chars": len(text),
        "text_truncated": False,
        "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20210517000667",
        "error_type": "ValueError",
        "error": "synthetic parser failure",
    }
    diagnostic_path.write_text(json.dumps(payload), encoding="utf-8")


def test_layout_profiler_fingerprints_preserved_failure_bundles(tmp_path: Path) -> None:
    for index, period_id in enumerate(_PERIODS):
        _write_failure(tmp_path, period_id, index)

    profiles = profile_historical_expansion_failures(output=tmp_path)

    assert tuple(item.period_id for item in profiles) == _PERIODS
    assert all(item.context_count == 1 for item in profiles)
    assert all(dict(item.signal_counts)["D램"] == 1 for item in profiles)
    assert all(dict(item.signal_counts)["낸드플래시"] == 1 for item in profiles)
    assert all(item.contexts[0].has_three_month_marker for item in profiles)
    assert all(item.contexts[0].has_cumulative_marker for item in profiles)
    assert all(item.contexts[0].unit_markers == ("백만원",) for item in profiles)
    assert all(item.contexts[0].amount_token_count == 4 for item in profiles)
    assert all(item.archive_member_count == 2 for item in profiles)
    assert all(dict(item.archive_member_suffix_counts) == {".txt": 1, ".xml": 1} for item in profiles)
    assert all(not item.parser_family_inferred for item in profiles)
    assert all(not item.product_revenue_extracted for item in profiles)
    assert all(not item.source_certification_promoted for item in profiles)
    assert all(not item.training_row_promoted for item in profiles)
    assert all(not item.fit_enabled for item in profiles)
