from pathlib import Path

path = Path("src/alpha_cycle/research_package_integrity_v2_1.py")
text = path.read_text(encoding="utf-8")
old = """    DECISION_VIEW_SCHEMA_VERSION,\n    DecisionExpectationGapSnapshot,\n    build_decision_view,\n    DecisionViewSelectionMethod,\n    DecisionViewSelectionRuleSnapshot,\n    DecisionViewSnapshot,\n"""
new = """    DECISION_VIEW_SCHEMA_VERSION,\n    DecisionExpectationGapSnapshot,\n    DecisionViewSelectionMethod,\n    DecisionViewSelectionRuleSnapshot,\n    DecisionViewSnapshot,\n    build_decision_view,\n"""
if text.count(old) != 1:
    raise SystemExit("expected import block not found exactly once")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
