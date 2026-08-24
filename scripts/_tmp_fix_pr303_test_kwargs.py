from pathlib import Path

path = Path("tests/unit/test_research_package_last_review_v2_1.py")
text = path.read_text(encoding="utf-8")
old = 'monkeypatch.setattr(assembler, "package_integrity_blocker_codes", lambda *args: ())'
new = 'monkeypatch.setattr(\n        assembler,\n        "package_integrity_blocker_codes",\n        lambda *args, **kwargs: (),\n    )'
count = text.count(old)
assert count == 3, count
text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
