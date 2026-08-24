from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# CSV round-trips may materialize boolean columns as numpy.bool_.  Accept only
# actual Python/numpy booleans, then compare their canonical Python value.
SOURCE = "src/alpha_cycle/research_package_source_revalidation_v2_1.py"
replace_once(SOURCE, "import pandas as pd\n", "import numpy as np\nimport pandas as pd\n")
replace_once(
    SOURCE,
    '''        raw_priced = row.get("priced")
        if not isinstance(raw_priced, bool):
            return False
        expected_priced = price is not None
        if raw_priced is not expected_priced:
            return False
''',
    '''        raw_priced = row.get("priced")
        if not isinstance(raw_priced, (bool, np.bool_)):
            return False
        expected_priced = price is not None
        if bool(raw_priced) is not expected_priced:
            return False
''',
)

# Keep a duplicate creation-time file descriptor open through final pathname
# validation and any rollback.  The original inode therefore cannot be recycled
# for a foreign replacement before ownership cleanup finishes.
ASSEMBLER = "src/alpha_cycle/research_package_assembler_v2_1.py"
replace_once(
    ASSEMBLER,
    '''    fd = os.open(path, flags, 0o644)
    created = os.fstat(fd)
    try:
''',
    '''    fd = os.open(path, flags, 0o644)
    created = os.fstat(fd)
    owned_fd = os.dup(fd)
    try:
''',
)
replace_once(
    ASSEMBLER,
    '''    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            _unlink_file_if_inode_matches(path, created.st_ino)
        except BaseException:
            pass
        raise


def _unlink_file_if_inode_matches''',
    '''    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            _unlink_file_if_inode_matches(path, created.st_ino)
        except BaseException:
            pass
        raise
    finally:
        os.close(owned_fd)


def _unlink_file_if_inode_matches''',
)

# The ENOSPC regression should fail the attempted new publication once, not the
# independent rollback hard-link used to restore the previously published pointer.
TEST = "tests/unit/test_research_package_exact_head_review_round2_v2_1.py"
replace_once(
    TEST,
    '''    real_link = os.link

    def failing_link(src, dst, *args, **kwargs):
        if Path(dst) == pointer and not pointer.exists():
            raise OSError(errno.ENOSPC, "injected no space")
        return real_link(src, dst, *args, **kwargs)
''',
    '''    real_link = os.link
    failed_publication = False

    def failing_link(src, dst, *args, **kwargs):
        nonlocal failed_publication
        if Path(dst) == pointer and not pointer.exists() and not failed_publication:
            failed_publication = True
            raise OSError(errno.ENOSPC, "injected no space")
        return real_link(src, dst, *args, **kwargs)
''',
)

print("PR303 final hardening follow-up applied")
