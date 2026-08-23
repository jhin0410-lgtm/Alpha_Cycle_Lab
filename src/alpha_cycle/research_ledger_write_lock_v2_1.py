"""Shared local write lock for append-only research-ledger mutations."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_LOCK_NAME = ".research_run_ledger.lock"


@contextmanager
def exclusive_research_ledger_write_lock(artifact_root: str | Path) -> Iterator[None]:
    """Serialize local request/run ledger writers and fail closed on an existing lock."""

    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / _LOCK_NAME
    fd: int | None = None
    created = False
    try:
        fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
        yield
    finally:
        if fd is not None:
            os.close(fd)
        if created:
            lock_path.unlink(missing_ok=True)
