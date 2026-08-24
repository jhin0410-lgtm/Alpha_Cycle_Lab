from __future__ import annotations

import tempfile
from pathlib import Path
from runpy import run_path

import pandas as pd

from alpha_cycle.intelligence.valuation import _valuation_metrics
from alpha_cycle.research_package_source_revalidation_v2_1 import (
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
    loaded = load_canonical_valuation_evidence(root, expected.snapshot_id)
    print("EXPECTED_ID", expected.snapshot_id)
    print("LOADED_NONE", loaded is None)
    if loaded is None:
        raise SystemExit(1)
    print("LOADED_ID", loaded.snapshot_id)
    print("RAW", loaded.raw_valuation)
    print("SHARES_DTYPES", loaded.shares.dtypes.astype(str).to_dict())
    print("VALUES_DTYPES", loaded.security_values.dtypes.astype(str).to_dict())
    print("METRICS_DTYPES", loaded.valuation_metrics.dtypes.astype(str).to_dict())
    print("SHARES", loaded.shares.to_dict(orient="records"))
    print("VALUES", loaded.security_values.to_dict(orient="records"))
    print("METRICS", loaded.valuation_metrics.to_dict(orient="records"))
    recomputed = _valuation_metrics(loaded.security_values, loaded.financial_history)
    print("RECOMPUTED", recomputed.to_dict(orient="records"))
    try:
        pd.testing.assert_frame_equal(
            recomputed.reset_index(drop=True),
            loaded.valuation_metrics.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-6,
        )
        print("FRAME_EQUAL", True)
    except AssertionError as exc:
        print("FRAME_EQUAL", False)
        print("FRAME_DIFF", str(exc))
    print("SEMANTICS_MATCH", _valuation_evidence_semantics_match(loaded))
