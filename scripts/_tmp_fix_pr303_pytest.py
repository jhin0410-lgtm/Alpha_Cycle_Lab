from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"expected exactly one match in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    Path("src/alpha_cycle/research_package_integrity_v2_1.py"),
    """        view.guardrail_evidence_id != active.evidence_id\n        or rule.guardrail_evidence_id != active.evidence_id\n""",
    """        getattr(view, \"guardrail_evidence_id\", None) != active.evidence_id\n        or rule.guardrail_evidence_id != active.evidence_id\n""",
)

replace_once(
    Path("tests/unit/test_research_package_assembler_v2_1.py"),
    """        tournament_forecast_snapshot_ids=(\n            selected_registration.snapshot_id,\n            benchmark_registration.snapshot_id,\n        ),\n""",
    """        tournament_forecast_snapshot_ids=tuple(\n            sorted(\n                (\n                    selected_registration.snapshot_id,\n                    benchmark_registration.snapshot_id,\n                )\n            )\n        ),\n""",
)
