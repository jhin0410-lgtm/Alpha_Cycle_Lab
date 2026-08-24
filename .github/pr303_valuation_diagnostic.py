from __future__ import annotations

import json
import tempfile
from pathlib import Path
from runpy import run_path

import pandas as pd

from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot, _valuation_metrics
from alpha_cycle.research_package_source_revalidation_v2_1 import (
    _find_valuation_directory,
    _read_json_regular,
    _read_valuation_csv,
    _valuation_evidence_semantics_match,
    load_canonical_valuation_evidence,
)

fixture = run_path("tests/unit/test_research_package_assembler_v2_1.py")
prepare = fixture["_prepare_ready_request"]
persist = fixture["_persist_components"]
components_fn = fixture["_components"]

with tempfile.TemporaryDirectory() as name:
    root = Path(name)
    theses = prepare(root)
    persist(root, theses)
    expected = components_fn(theses[0], 0)[12]
    directory = _find_valuation_directory(root, expected.snapshot_id)
    print("EXPECTED_ID", expected.snapshot_id)
    print("DIRECTORY", directory)
    if directory is None:
        raise SystemExit("valuation directory not found")
    manifest = _read_json_regular(directory / "manifest.json", root)
    shares = _read_valuation_csv(directory / "shares.csv", root)
    values = _read_valuation_csv(directory / "security_values.csv", root)
    history = _read_valuation_csv(directory / "financial_history.csv", root)
    metrics = _read_valuation_csv(directory / "valuation_metrics.csv", root)
    raw = _read_json_regular(directory / "raw_valuation.json", root)
    reconstructed = ValuationEvidenceSnapshot(
        captured_at=expected.captured_at,
        evaluation_date=expected.evaluation_date,
        research_snapshot_id=expected.research_snapshot_id,
        market_snapshot_id=expected.market_snapshot_id,
        history_years=expected.history_years,
        shares=shares,
        security_values=values,
        financial_history=history,
        valuation_metrics=metrics,
        raw_valuation=raw,
        warnings=expected.warnings,
    )
    print("RECONSTRUCTED_ID", reconstructed.snapshot_id)
    print("ID_MATCH", reconstructed.snapshot_id == expected.snapshot_id)
    for label, before, after in (
        ("SHARES", expected.shares, shares),
        ("VALUES", expected.security_values, values),
        ("HISTORY", expected.financial_history, history),
        ("METRICS", expected.valuation_metrics, metrics),
    ):
        print(label + "_DTYPES_BEFORE", before.dtypes.astype(str).to_dict())
        print(label + "_DTYPES_AFTER", after.dtypes.astype(str).to_dict())
        print(label + "_BEFORE", before.to_dict(orient="records"))
        print(label + "_AFTER", after.to_dict(orient="records"))
        try:
            pd.testing.assert_frame_equal(before, after, check_dtype=False, check_exact=False)
            print(label + "_FRAME_EQUAL", True)
        except AssertionError as exc:
            print(label + "_FRAME_EQUAL", False)
            print(label + "_FRAME_DIFF", str(exc))
    before_payload = expected.payload_without_id()
    after_payload = reconstructed.payload_without_id()
    for key in ("shares", "security_values", "financial_history", "valuation_metrics", "raw_valuation"):
        if before_payload[key] != after_payload[key]:
            print("PAYLOAD_DIFF_KEY", key)
            print("PAYLOAD_BEFORE", json.dumps(before_payload[key], ensure_ascii=False, sort_keys=True))
            print("PAYLOAD_AFTER", json.dumps(after_payload[key], ensure_ascii=False, sort_keys=True))
    recomputed = _valuation_metrics(values, history)
    try:
        pd.testing.assert_frame_equal(
            recomputed.reset_index(drop=True),
            metrics.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-6,
        )
        print("RECOMPUTED_FRAME_EQUAL", True)
    except AssertionError as exc:
        print("RECOMPUTED_FRAME_EQUAL", False)
        print("RECOMPUTED_DIFF", str(exc))
    print("SEMANTICS_MATCH_RECONSTRUCTED", _valuation_evidence_semantics_match(reconstructed))
    loaded = load_canonical_valuation_evidence(root, expected.snapshot_id)
    print("CANONICAL_LOADER_NONE", loaded is None)
