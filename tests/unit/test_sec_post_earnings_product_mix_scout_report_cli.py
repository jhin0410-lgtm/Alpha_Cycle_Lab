from __future__ import annotations

import json
from datetime import date

import pytest

import alpha_cycle.sec_post_earnings_product_mix_scout_report_cli as report_cli
from alpha_cycle.intelligence.sec_post_earnings_product_mix_scout import (
    SecPostEarningsFiling,
    SecPostEarningsScoutEvidence,
    SecPostEarningsScoutResult,
)


_SHA = "a" * 64


def _evidence() -> SecPostEarningsScoutEvidence:
    filings = (
        SecPostEarningsFiling(
            accession_number="0001193125-26-341163",
            filing_date=date(2026, 8, 10),
            form="6-K",
            primary_document="d64707d6k.htm",
        ),
        SecPostEarningsFiling(
            accession_number="0001193125-26-339031",
            filing_date=date(2026, 8, 7),
            form="6-K",
            primary_document="d123529d6k.htm",
        ),
    )
    results = (
        SecPostEarningsScoutResult(
            accession_number=filings[0].accession_number,
            filing_date=filings[0].filing_date,
            primary_document=filings[0].primary_document,
            filing_sha256=_SHA,
            filing_bytes=100,
            visible_text_sha256=_SHA,
            visible_text_chars=80,
            q2_period_anchor=False,
            dram_anchor=False,
            nand_anchor=False,
            other_products_anchor=False,
            revenue_anchor=False,
            classification="no_product_mix_signal",
            candidate_for_manual_parser_review=False,
        ),
        SecPostEarningsScoutResult(
            accession_number=filings[1].accession_number,
            filing_date=filings[1].filing_date,
            primary_document=filings[1].primary_document,
            filing_sha256=_SHA,
            filing_bytes=200,
            visible_text_sha256=_SHA,
            visible_text_chars=150,
            q2_period_anchor=False,
            dram_anchor=True,
            nand_anchor=False,
            other_products_anchor=False,
            revenue_anchor=True,
            classification="memory_mentions_only",
            candidate_for_manual_parser_review=False,
        ),
    )
    return SecPostEarningsScoutEvidence(
        evidence_id=_SHA,
        observed_date=date(2026, 8, 15),
        after_date=date(2026, 7, 29),
        submissions_sha256=_SHA,
        filings=filings,
        results=results,
    )


def test_report_reverifies_and_explains_zero_candidates(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_load(pointer_path, *, evaluation_date):
        assert str(pointer_path).endswith("pointer.json")
        assert evaluation_date == date(2026, 8, 15)
        return _evidence()

    monkeypatch.setattr(
        report_cli,
        "load_post_earnings_product_mix_scout_evidence",
        fake_load,
    )
    assert (
        report_cli.main(
            [
                "--pointer",
                "pointer.json",
                "--evaluation-date",
                "2026-08-15",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "sec_post_earnings_product_mix_scout_reverified"
    assert payload["candidate_count"] == 0
    assert payload["candidate_accessions"] == []
    assert payload["classification_counts"] == {
        "memory_mentions_only": 1,
        "no_product_mix_signal": 1,
    }
    assert payload["filing_summaries"][0]["form"] == "6-K"
    assert payload["filing_summaries"][0]["q2_period_anchor"] is False
    assert payload["filing_summaries"][1]["dram_anchor"] is True
    assert payload["product_baseline_eligible"] is False
    assert payload["allocation_resolver_registered"] is False
    assert payload["numeric_forecast_enabled"] is False
    assert payload["decision_score_enabled"] is False
