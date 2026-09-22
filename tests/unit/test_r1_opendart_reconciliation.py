from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import timedelta
from email.message import Message
from http.client import IncompleteRead
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from test_r1_opendart_observations import selection
from test_valuation_authority_v2_1 import CAPTURED, _research

import alpha_cycle.intelligence.r1_opendart_reconciliation as reconciliation
from alpha_cycle.intelligence.fundamental_macro import write_fundamental_macro_snapshot
from alpha_cycle.intelligence.r1_opendart_observations import load_opendart_universe


def setup_source(tmp_path):
    source = _research("a" * 64)
    directory = write_fundamental_macro_snapshot(tmp_path, source)[0].parent
    return source, directory


def reconcile(directory, capture, *, at=CAPTURED):
    return reconciliation.reconcile_opendart_capture(
        directory, selections=(selection(),), official_capture=capture, verified_at=at,
    )


def test_official_looking_capture_and_offline_replay_are_not_live_authority(tmp_path):
    source, directory = setup_source(tmp_path / "source")
    report = reconcile(directory, source.raw_opendart)
    assert not report.fresh_official_verification
    claims = json.loads(report.claims_json)
    assert claims[0]["value"] == 42_947_902_000_000
    assert claims[0]["filing_receipt"] == "20260317000635"
    assert claims[0]["authority_available_at"] == CAPTURED.isoformat()
    path = reconciliation.persist_opendart_reconciliation(report, tmp_path / "reports")
    assert reconciliation.persist_opendart_reconciliation(report, path.parent) == path
    replay = reconciliation.replay_opendart_reconciliation(
        path, directory, selections=(selection(),)
    )
    assert replay.content_id == report.content_id
    assert not replay.fresh_official_verification


@pytest.mark.parametrize("field,value", [
    ("thstrm_amount", "1"), ("rcept_no", "20260318000635"),
    ("stock_code", "005930"), ("bsns_year", "2024"),
    ("reprt_code", "11012"), ("currency", "USD"),
    ("account_id", "future_eps"),
])
def test_independent_capture_must_match_exact_claim(tmp_path, field, value):
    source, directory = setup_source(tmp_path)
    raw = copy.deepcopy(source.raw_opendart)
    row = next(item for item in raw["000660"]["financial"]["financials"]["list"]
               if item["account_id"] == "ifrs-full_ProfitLoss")
    row[field] = value
    with pytest.raises(ValueError):
        reconcile(directory, raw)


def test_verification_cannot_precede_acquisition(tmp_path):
    source, directory = setup_source(tmp_path)
    with pytest.raises(ValueError, match="capture exceeds"):
        reconcile(directory, source.raw_opendart, at=source.captured_at - timedelta(seconds=1))


@pytest.mark.parametrize("url", [
    "http://opendart.fss.or.kr/api/company.json", "https://example.com/api/company.json",
    "https://opendart.fss.or.kr:443/api/company.json",
])
def test_authority_transport_rejects_unpinned_origins_before_io(url):
    with pytest.raises(ValueError, match="pinned HTTPS"):
        reconciliation._OfficialOpenDartTransport().get(url, headers={}, timeout_seconds=1)


def test_authority_transport_does_not_delegate_authority_by_redirect():
    with pytest.raises(ValueError, match="rejects redirects"):
        reconciliation._NoAuthorityRedirect().redirect_request()


@pytest.mark.parametrize("error_response", [False, True])
def test_interrupted_response_is_normalized_without_body_or_credential_leak(
    monkeypatch, error_response,
):
    url = "https://opendart.fss.or.kr/api/company.json"

    class Interrupted:
        status = 200
        headers = Message()

        def geturl(self):
            return url

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, *args):
            raise IncompleteRead(b"private partial body", 100)

        def close(self):
            pass

    def open_response(*args, **kwargs):
        if error_response:
            raise HTTPError(url, 503, "unavailable", Message(), Interrupted())
        return Interrupted()

    monkeypatch.setattr(reconciliation, "build_opener", lambda *a: SimpleNamespace(
        open=open_response
    ))
    with pytest.raises(OSError, match="official authority") as error:
        reconciliation._OfficialOpenDartTransport().get(url, headers={}, timeout_seconds=1)
    assert "private partial" not in str(error.value)


def test_copy_replace_and_mutation_cannot_inherit_issuance(tmp_path):
    source, directory = setup_source(tmp_path)
    report = reconcile(directory, source.raw_opendart)
    # Test only the in-process issuance boundary. This synthetic report was not
    # fetched from a provider and is never used as a live acceptance receipt.
    reconciliation._LIVE_VERIFICATIONS[report] = report.content_id
    assert report.fresh_official_verification
    assert not copy.copy(report).fresh_official_verification
    assert not replace(report).fresh_official_verification
    changed = json.loads(report.claims_json)
    changed[0]["value"] = 1
    object.__setattr__(report, "claims_json", json.dumps(changed))
    assert not report.fresh_official_verification


def test_consumer_rejects_detached_claims_and_backdated_cutoff(tmp_path):
    source, directory = setup_source(tmp_path)
    report = reconcile(directory, source.raw_opendart, at=CAPTURED + timedelta(seconds=1))
    universe = load_opendart_universe(
        directory, selections=(selection(),), universe_id="test", version="1",
        cutoff_at=CAPTURED + timedelta(seconds=2),
    )
    with pytest.raises(ValueError, match="fresh official"):
        reconciliation.require_reconciled_universe(report, universe)
    reconciliation._LIVE_VERIFICATIONS[report] = report.content_id
    reconciliation.require_reconciled_universe(report, universe)
    with pytest.raises(ValueError, match="exceeds"):
        reconciliation.require_reconciled_universe(
            report, replace(universe, research_cutoff_at=CAPTURED)
        )
    other = replace(universe.observations[0], value=1)
    with pytest.raises(ValueError, match="exactly cover"):
        reconciliation.require_reconciled_universe(report, replace(universe, observations=(other,)))


def test_changed_serialized_claim_is_rejected_and_conflicts_never_overwrite(tmp_path):
    source, directory = setup_source(tmp_path / "source")
    report = reconcile(directory, source.raw_opendart)
    path = reconciliation.persist_opendart_reconciliation(report, tmp_path / "reports")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["claims"][0]["metric_id"] = "future_eps"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="reconstruction mismatch"):
        reconciliation.replay_opendart_reconciliation(path, directory, selections=(selection(),))
    with pytest.raises(ValueError, match="conflicts"):
        reconciliation.persist_opendart_reconciliation(report, path.parent)


def test_source_swap_during_official_retrieval_cannot_issue_authority(tmp_path, monkeypatch):
    source, directory = setup_source(tmp_path)
    changed = replace(source, captured_at=source.captured_at + timedelta(seconds=1))
    generations = iter((source, changed))
    monkeypatch.setattr(reconciliation, "revalidate_research_snapshot", lambda _: next(generations))
    corp = SimpleNamespace(corp_code="00164779", stock_code="000660")
    client = SimpleNamespace(
        resolve_stock_codes=lambda _: {"000660": corp},
        financial_statements=lambda *a, **kw: SimpleNamespace(
            raw_payload=source.raw_opendart["000660"]["financial"]
        ),
    )
    monkeypatch.setattr(reconciliation.OpenDartCredentials, "from_env", lambda: None)
    monkeypatch.setattr(reconciliation, "OpenDartReadOnlyClient", lambda *a, **kw: client)
    with pytest.raises(ValueError, match="generation changed"):
        reconciliation.verify_opendart_reported_fields(directory, selections=(selection(),))
