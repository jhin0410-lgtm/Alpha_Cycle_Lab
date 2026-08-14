from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import alpha_cycle.intelligence.sec_post_earnings_product_mix_scout as scout_module
from alpha_cycle.intelligence.sec_post_earnings_product_mix_scout import (
    build_post_earnings_scout_evidence,
    capture_post_earnings_product_mix_scout,
    classify_post_earnings_6k,
    discover_post_earnings_6k_filings,
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
                        "0001193125-26-336490",
                        "0001193125-26-321989",
                        "0001193125-26-299963",
                    ],
                    "filingDate": [
                        "2026-08-10",
                        "2026-08-07",
                        "2026-08-06",
                        "2026-07-29",
                        "2026-07-10",
                    ],
                    "form": ["6-K", "6-K", "6-K", "6-K", "424B4"],
                    "primaryDocument": [
                        "d64707d6k.htm",
                        "d123529d6k.htm",
                        "d174813d6k.htm",
                        "d115239d6k.htm",
                        "d32785d424b4.htm",
                    ],
                }
            },
        }
    ).encode("utf-8")


def _full_candidate() -> bytes:
    return b"""<html><body>
    Second quarter of 2026 revenue by product category.
    DRAM revenue was presented together with NAND flash and Other products revenue.
    </body></html>"""


def _memory_candidate() -> bytes:
    return b"""<html><body>
    For the three months ended June 30, 2026, DRAM and NAND market conditions changed.
    </body></html>"""


def _memory_only() -> bytes:
    return b"<html><body>DRAM demand remained strong.</body></html>"


def _no_signal() -> bytes:
    return b"<html><body>Corporate governance update.</body></html>"


def test_discovery_uses_only_post_cutoff_6k_filings() -> None:
    filings = discover_post_earnings_6k_filings(
        _submissions(),
        after_date=AFTER,
        observed_date=OBSERVED,
    )
    assert [item.accession_number for item in filings] == [
        "0001193125-26-341163",
        "0001193125-26-339031",
        "0001193125-26-336490",
    ]
    assert [item.primary_document for item in filings] == [
        "d64707d6k.htm",
        "d123529d6k.htm",
        "d174813d6k.htm",
    ]


def test_classifier_requires_q2_dram_nand_and_other_for_full_candidate() -> None:
    filings = discover_post_earnings_6k_filings(
        _submissions(),
        after_date=AFTER,
        observed_date=OBSERVED,
    )
    full = classify_post_earnings_6k(filings[0], _full_candidate())
    memory = classify_post_earnings_6k(filings[1], _memory_candidate())
    memory_only = classify_post_earnings_6k(filings[2], _memory_only())

    assert full.classification == "q2_full_revenue_candidate"
    assert full.candidate_for_manual_parser_review is True
    assert full.q2_period_anchor is True
    assert full.dram_anchor is True
    assert full.nand_anchor is True
    assert full.other_products_anchor is True
    assert full.revenue_anchor is True

    assert memory.classification == "q2_memory_candidate"
    assert memory.candidate_for_manual_parser_review is True
    assert memory.other_products_anchor is False

    assert memory_only.classification == "memory_mentions_only"
    assert memory_only.candidate_for_manual_parser_review is False


def test_build_requires_exact_downloaded_filing_set_and_never_promotes_candidates() -> None:
    filing_bytes = {
        "0001193125-26-341163": _full_candidate(),
        "0001193125-26-339031": _memory_candidate(),
        "0001193125-26-336490": _no_signal(),
    }
    evidence = build_post_earnings_scout_evidence(
        observed_date=OBSERVED,
        after_date=AFTER,
        submissions_bytes=_submissions(),
        filing_bytes_by_accession=filing_bytes,
    )
    assert len(evidence.filings) == 3
    assert [item.classification for item in evidence.results] == [
        "q2_full_revenue_candidate",
        "q2_memory_candidate",
        "no_product_mix_signal",
    ]
    assert evidence.discovery_only is True
    assert evidence.product_baseline_eligible is False
    assert evidence.allocation_resolver_registered is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False

    missing = dict(filing_bytes)
    missing.pop("0001193125-26-336490")
    with pytest.raises(ValueError, match="must match discovered filings exactly"):
        build_post_earnings_scout_evidence(
            observed_date=OBSERVED,
            after_date=AFTER,
            submissions_bytes=_submissions(),
            filing_bytes_by_accession=missing,
        )


def test_capture_archives_exact_official_submission_and_primary_document_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by_document = {
        "d64707d6k.htm": _full_candidate(),
        "d123529d6k.htm": _memory_candidate(),
        "d174813d6k.htm": _no_signal(),
    }

    def fake_download(url: str, *, user_agent: str, timeout_seconds: float = 20.0) -> bytes:
        assert "@" in user_agent
        assert timeout_seconds > 0
        if "submissions" in url:
            return _submissions()
        for document, payload in by_document.items():
            if url.endswith(document):
                return payload
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(scout_module, "download_sec_bytes", fake_download)
    output = tmp_path / "scout"
    result = capture_post_earnings_product_mix_scout(
        observed_date=OBSERVED,
        after_date=AFTER,
        user_agent="AlphaCycleLab research@example.com",
        output=output,
        captured_at=datetime(2026, 8, 15, 2, 0, tzinfo=UTC),
    )
    artifact = Path(str(result["artifact_directory"]))
    assert (artifact / "sec_submissions.json").read_bytes() == _submissions()
    assert (artifact / "0001193125-26-341163__d64707d6k.htm").read_bytes() == (
        _full_candidate()
    )
    assert result["candidate_count"] == 2
    assert result["candidate_accessions"] == [
        "0001193125-26-341163",
        "0001193125-26-339031",
    ]
    assert result["discovery_only"] is True
    assert result["product_baseline_eligible"] is False
    assert result["allocation_resolver_registered"] is False


def test_scout_refuses_wrong_cik_or_non_future_observation() -> None:
    wrong = json.loads(_submissions())
    wrong["cik"] = "0000000001"
    with pytest.raises(ValueError, match="not SK hynix"):
        discover_post_earnings_6k_filings(
            json.dumps(wrong).encode("utf-8"),
            after_date=AFTER,
            observed_date=OBSERVED,
        )
    with pytest.raises(ValueError, match="must be after"):
        discover_post_earnings_6k_filings(
            _submissions(),
            after_date=AFTER,
            observed_date=AFTER,
        )
