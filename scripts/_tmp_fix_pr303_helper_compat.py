from pathlib import Path

path = Path("src/alpha_cycle/research_package_assembler_v2_1.py")
text = path.read_text(encoding="utf-8")
old = "    artifact_root: Path,\n    blockers: list[ResearchRoundBlocker],\n"
new = "    artifact_root: Path | None = None,\n    blockers: list[ResearchRoundBlocker],\n"
if text.count(old) != 1:
    raise SystemExit("unexpected _assemble_security_package signature")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
