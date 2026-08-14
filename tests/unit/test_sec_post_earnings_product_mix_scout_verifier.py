from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import alpha_cycle.intelligence.sec_post_earnings_product_mix_scout as scout_module
from alpha_cycle.intelligence.sec_post_earnings_product_mix_scout import (
    capture_post_earnings_product_mix_scout,
)
from alpha_cycle.intelligence.sec_post_earnings_product_mix_scout_verifier import (
    load_post_earnings_product_mix_scout_evidence,
)

OBSERVED = date(2026, 8, 15)
AFTER = date(2026, 7, 29)


def _submissions() -> bytes:
    return json.dumps(
        {
            "cik": "0002120882",
            "filings": {
                "recent": {
                    "accessionNumber": [
                        "0001193125-26-341163",
                        "0001193125-26-339031",
                    ],
                    "filingDate": ["2026-08-10", "2026-08-07"],
                    "form": ["6-K", "6-K"],
                    "primaryDocument": ["d64707d6k.htm", "d123529d6k.htm"],
                }
            },
        }
    ).encode("utf-8")


def _full_candidate() -> bytes:
    return b"""<html><body>
    Second quarter of 2026 revenue by product category.
    DRAM revenue was presented together with NAND flash and Other products revenue.
    </body></html>"""


def _no_signal() -> bytes:
    return b"<html><body>Corporate governance update.</body></html>"


def _capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    def fake_download(url: str, *, user_agent: str, timeout_seconds: float = 20.0) -> bytes:
        assert "@" in user_agent
        assert timeout_seconds > 0
        if "submissions" in url:
            return _submissions()
        if url.endswith("d64707d6k.htm"):
            return _full_candidate()
        if url.endswith("d123529d6k.htm"):
            return _no_signal()
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(scout_module, "download_sec_bytes", fake_download)
    output = tmp_path / "scout"
    capture_post_earnings_product_mix_scout(
        observed_date=OBSERVED,
        after_date=AFTER,
        user_agent="AlphaCycleLab research@example.com",
        output=output,
        captured_at=datetime(2026, 8, 15, 2, 0, tzinfo=UTC),
    )
    return output / "latest_sec_post_earnings_product_mix_scout.json"


def test_verifier_rebuilds_candidate_list_from_archived_source_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer = _capture(tmp_path, monkeypatch)
    evidence = load_post_earnings_product_mix_scout_evidence(
        pointer,
        evaluation_date=OBSERVED,
    )
    assert [item.accession_number for item in evidence.filings] == [
        "0001193125-26-341163",
        "0001193125-26-339031",
    ]
    assert [item.classification for item in evidence.results] == [
        "q2_full_revenue_candidate",
        "no_product_mix_signal",
    ]
    assert evidence.product_baseline_eligible is False
    assert evidence.allocation_resolver_registered is False


def test_verifier_rejects_archived_filing_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer = _capture(tmp_path, monkeypatch)
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    artifact = Path(payload["artifact_directory"])
    filing = artifact / "0001193125-26-341163__d64707d6k.htm"
    filing.write_bytes(b"<html><body>tampered</body></html>")
    with pytest.raises(ValueError, match="does not reproduce"):
        load_post_earnings_product_mix_scout_evidence(
            pointer,
            evaluation_date=OBSERVED,
        )


def test_verifier_rejects_persisted_candidate_promotion_or_result_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer = _capture(tmp_path, monkeypatch)
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    payload["product_baseline_eligible"] = True
    pointer.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="product_baseline_eligible=false"):
        load_post_earnings_product_mix_scout_evidence(
            pointer,
            evaluation_date=OBSERVED,
        )

    pointer = _capture(tmp_path / "second", monkeypatch)
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    results_path = Path(payload["scout_results_path"])
    results = json.loads(results_path.read_text(encoding="utf-8"))
    results[0]["classification"] = "q2_full_revenue_candidate"
    results[0]["candidate_for_manual_parser_review"] = False
    results_path.write_text(json.dumps(results), encoding="utf-8")
    with pytest.raises(ValueError, match="persisted result mismatch"):
        load_post_earnings_product_mix_scout_evidence(
            pointer,
            evaluation_date=OBSERVED,
        )


def test_verifier_refuses_backdating_before_observed_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer = _capture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="not yet observed"):
        load_post_earnings_product_mix_scout_evidence(
            pointer,
            evaluation_date=date(2026, 8, 14),
        )
