from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import alpha_cycle.intelligence.sec_post_earnings_all_form_inventory as inventory_module
from alpha_cycle.intelligence.sec_post_earnings_all_form_inventory import (
    build_post_earnings_all_form_evidence,
    capture_post_earnings_all_form_inventory,
    classify_post_earnings_primary_html,
    discover_post_earnings_primary_html_filings,
)
from alpha_cycle.intelligence.sec_post_earnings_all_form_inventory_verifier import (
    load_post_earnings_all_form_inventory_evidence,
)

OBSERVED_DATE = date(2026, 8, 15)
AFTER_DATE = date(2026, 7, 29)


def _submissions() -> bytes:
    payload = {
        "cik": "2120882",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0001193125-26-350177",
                    "0001193125-26-349900",
                    "0001193125-26-349800",
                    "0001193125-26-349700",
                    "0001193125-26-321989",
                ],
                "filingDate": [
                    "2026-08-14",
                    "2026-08-13",
                    "2026-08-12",
                    "2026-08-11",
                    "2026-07-29",
                ],
                "form": ["6-K", "424B4", "FWP", "EFFECT", "6-K"],
                "primaryDocument": [
                    "d158635d6k.htm",
                    "d200000d424b4.htm",
                    "d200001dfwp.htm",
                    "xslEFFECTX01/primary_doc.xml",
                    "d115239d6k.htm",
                ],
            }
        },
    }
    return json.dumps(payload).encode()


def _filing_bytes() -> dict[str, bytes]:
    return {
        "0001193125-26-350177": b"<html><body>Unrelated corporate filing</body></html>",
        "0001193125-26-349900": (
            b"<html><body>Three months ended June 30, 2026 Revenue DRAM NAND "
            b"Other products</body></html>"
        ),
        "0001193125-26-349800": b"<html><body>DRAM product update</body></html>",
    }


def test_discovery_includes_non_6k_primary_html_and_excludes_cutoff_non_html() -> None:
    filings = discover_post_earnings_primary_html_filings(
        _submissions(),
        after_date=AFTER_DATE,
        observed_date=OBSERVED_DATE,
    )
    assert [(item.form, item.accession_number) for item in filings] == [
        ("6-K", "0001193125-26-350177"),
        ("424B4", "0001193125-26-349900"),
        ("FWP", "0001193125-26-349800"),
    ]


def test_all_form_candidate_is_discovery_only() -> None:
    filings = discover_post_earnings_primary_html_filings(
        _submissions(),
        after_date=AFTER_DATE,
        observed_date=OBSERVED_DATE,
    )
    result = classify_post_earnings_primary_html(
        filings[1],
        _filing_bytes()[filings[1].accession_number],
    )
    assert result.form == "424B4"
    assert result.classification == "q2_full_revenue_candidate"
    assert result.candidate_for_manual_parser_review is True
    assert result.product_baseline_eligible is False
    assert result.allocation_resolver_registered is False
    assert result.numeric_forecast_enabled is False
    assert result.decision_score_enabled is False


def test_evidence_requires_exact_discovered_byte_set() -> None:
    with pytest.raises(ValueError, match="byte set must match"):
        build_post_earnings_all_form_evidence(
            observed_date=OBSERVED_DATE,
            after_date=AFTER_DATE,
            submissions_bytes=_submissions(),
            filing_bytes_by_accession={
                "0001193125-26-350177": _filing_bytes()["0001193125-26-350177"]
            },
        )


def test_capture_and_verifier_reproduce_archived_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submissions = _submissions()
    filing_bytes = _filing_bytes()

    def fake_download(url: str, *, user_agent: str, timeout_seconds: float) -> bytes:
        assert user_agent == "AlphaCycleLab contact@example.com"
        assert timeout_seconds == 5.0
        if "submissions" in url:
            return submissions
        for accession, payload in filing_bytes.items():
            if accession.replace("-", "") in url:
                return payload
        raise AssertionError(url)

    monkeypatch.setattr(inventory_module, "download_sec_bytes", fake_download)
    pointer = capture_post_earnings_all_form_inventory(
        observed_date=OBSERVED_DATE,
        after_date=AFTER_DATE,
        user_agent="AlphaCycleLab contact@example.com",
        output=tmp_path,
        captured_at=datetime(2026, 8, 14, 16, 10, tzinfo=UTC),
        timeout_seconds=5.0,
    )
    assert pointer["filing_count"] == 3
    assert pointer["non_6k_filing_count"] == 2
    assert pointer["form_counts"] == {"424B4": 1, "6-K": 1, "FWP": 1}
    assert pointer["candidate_count"] == 1
    assert pointer["candidate_accessions"] == ["0001193125-26-349900"]
    assert pointer["product_baseline_eligible"] is False

    evidence = load_post_earnings_all_form_inventory_evidence(
        tmp_path / "latest_sec_post_earnings_all_form_inventory.json",
        evaluation_date=OBSERVED_DATE,
    )
    assert evidence.evidence_id == pointer["evidence_id"]
    assert [item.classification for item in evidence.results] == [
        "no_product_mix_signal",
        "q2_full_revenue_candidate",
        "memory_mentions_only",
    ]


def test_verifier_rejects_persisted_candidate_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submissions = _submissions()
    filing_bytes = _filing_bytes()

    def fake_download(url: str, *, user_agent: str, timeout_seconds: float) -> bytes:
        if "submissions" in url:
            return submissions
        for accession, payload in filing_bytes.items():
            if accession.replace("-", "") in url:
                return payload
        raise AssertionError(url)

    monkeypatch.setattr(inventory_module, "download_sec_bytes", fake_download)
    pointer = capture_post_earnings_all_form_inventory(
        observed_date=OBSERVED_DATE,
        after_date=AFTER_DATE,
        user_agent="AlphaCycleLab contact@example.com",
        output=tmp_path,
        captured_at=datetime(2026, 8, 14, 16, 20, tzinfo=UTC),
    )
    results_path = Path(str(pointer["inventory_results_path"]))
    raw = json.loads(results_path.read_text(encoding="utf-8"))
    raw[0]["classification"] = "q2_memory_candidate"
    raw[0]["candidate_for_manual_parser_review"] = True
    results_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="persisted result mismatch"):
        load_post_earnings_all_form_inventory_evidence(
            tmp_path / "latest_sec_post_earnings_all_form_inventory.json",
            evaluation_date=OBSERVED_DATE,
        )


def test_verifier_rejects_archived_filing_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submissions = _submissions()
    filing_bytes = _filing_bytes()

    def fake_download(url: str, *, user_agent: str, timeout_seconds: float) -> bytes:
        if "submissions" in url:
            return submissions
        for accession, payload in filing_bytes.items():
            if accession.replace("-", "") in url:
                return payload
        raise AssertionError(url)

    monkeypatch.setattr(inventory_module, "download_sec_bytes", fake_download)
    pointer = capture_post_earnings_all_form_inventory(
        observed_date=OBSERVED_DATE,
        after_date=AFTER_DATE,
        user_agent="AlphaCycleLab contact@example.com",
        output=tmp_path,
        captured_at=datetime(2026, 8, 14, 16, 30, tzinfo=UTC),
    )
    artifact = Path(str(pointer["artifact_directory"]))
    filing_path = artifact / "0001193125-26-349900__d200000d424b4.htm"
    filing_path.write_bytes(filing_path.read_bytes() + b" tampered")
    with pytest.raises(ValueError, match="does not reproduce"):
        load_post_earnings_all_form_inventory_evidence(
            tmp_path / "latest_sec_post_earnings_all_form_inventory.json",
            evaluation_date=OBSERVED_DATE,
        )
