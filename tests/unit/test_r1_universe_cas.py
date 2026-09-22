from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest
from test_observable_universe import T0, T1, T2, snapshot

import alpha_cycle.intelligence.observable_universe as universe_module
from alpha_cycle.intelligence.observable_universe import (
    ConcurrentUniverseUpdateError,
    load_current_universe_state,
    persist_successful_universe_attempt,
    publish_failed_universe_attempt,
)


def _publish(root: Path, at: datetime, success: bool, expected: str | None) -> None:
    if success:
        persist_successful_universe_attempt(
            snapshot(cutoff=at), output_root=root, attempted_at=at,
            expected_current_attempt_id=expected,
        )
    else:
        publish_failed_universe_attempt(
            output_root=root, attempted_at=at, failure_code="source_unavailable",
            expected_current_attempt_id=expected,
        )


def _attempt(root: Path) -> str:
    current = load_current_universe_state(root)
    assert current is not None
    return current.attempt_id


def _stored_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("parent_success", [False, True])
@pytest.mark.parametrize("next_success", [False, True])
def test_exact_success_or_failure_parent_can_advance(
    tmp_path: Path, parent_success: bool, next_success: bool,
) -> None:
    _publish(tmp_path, T0, parent_success, None)
    parent = _attempt(tmp_path)
    _publish(tmp_path, T1, next_success, parent)
    current = load_current_universe_state(tmp_path)
    assert current is not None and current.attempt_id != parent
    assert current.ready is next_success


@pytest.mark.parametrize("competing_success", [False, True])
@pytest.mark.parametrize("stale_success", [False, True])
def test_stale_parent_does_not_replace_competing_success_or_failure(
    tmp_path: Path, competing_success: bool, stale_success: bool,
) -> None:
    _publish(tmp_path, T0, True, None)
    parent = _attempt(tmp_path)
    _publish(tmp_path, T1, competing_success, parent)
    before = _stored_bytes(tmp_path)
    with pytest.raises(ConcurrentUniverseUpdateError, match="changed before publication"):
        _publish(tmp_path, T2, stale_success, parent)
    assert _stored_bytes(tmp_path) == before


@pytest.mark.parametrize("existing_success", [False, True])
@pytest.mark.parametrize("stale_success", [False, True])
def test_explicit_absence_rejects_any_existing_attempt(
    tmp_path: Path, existing_success: bool, stale_success: bool,
) -> None:
    _publish(tmp_path, T0, existing_success, None)
    before = _stored_bytes(tmp_path)
    with pytest.raises(ConcurrentUniverseUpdateError):
        _publish(tmp_path, T1, stale_success, None)
    assert _stored_bytes(tmp_path) == before


@pytest.mark.parametrize("success", [False, True])
def test_exact_parent_rejects_missing_store(tmp_path: Path, success: bool) -> None:
    with pytest.raises(ConcurrentUniverseUpdateError):
        _publish(tmp_path, T0, success, "a" * 64)
    assert load_current_universe_state(tmp_path) is None
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("initial_success", [False, True])
def test_competing_publishers_compare_parent_under_same_write_lock(
    tmp_path: Path, initial_success: bool,
) -> None:
    if initial_success:
        _publish(tmp_path, T0, True, None)
    expected = _attempt(tmp_path) if initial_success else None
    barrier = threading.Barrier(2)

    def publish(at: datetime, success: bool) -> bool:
        barrier.wait(timeout=10)
        try:
            _publish(tmp_path, at, success, expected)
        except ConcurrentUniverseUpdateError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        success_future = executor.submit(publish, T1, True)
        failure_future = executor.submit(publish, T2, False)
        success_won = success_future.result(timeout=20)
        failure_won = failure_future.result(timeout=20)
    assert success_won != failure_won
    current = load_current_universe_state(tmp_path)
    assert current is not None and current.ready is success_won
    assert current.attempted_at == (T1 if success_won else T2)


def test_omitting_expected_parent_preserves_legacy_publication(tmp_path: Path) -> None:
    _publish(tmp_path, T0, True, None)
    publish_failed_universe_attempt(
        output_root=tmp_path, attempted_at=T1, failure_code="source_unavailable",
    )
    persist_successful_universe_attempt(
        snapshot(cutoff=T2), output_root=tmp_path, attempted_at=T2,
    )
    current = load_current_universe_state(tmp_path)
    assert current is not None and current.ready


def test_first_writers_do_not_read_contended_lock_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / universe_module._WRITE_LOCK_PATH
    barrier = threading.Barrier(2)
    original_link = universe_module.os.link
    original_read = universe_module._read_regular_file

    def collide_links(source, destination):
        if Path(destination) == lock_path:
            # Both initializers saw an absent sentinel. One link must lose.
            barrier.wait(timeout=10)
        original_link(source, destination)

    def deny_sentinel_read(path: Path, label: str) -> bytes:
        if path == lock_path:
            raise PermissionError("Windows byte-range lock prevents reading sentinel")
        return original_read(path, label)

    monkeypatch.setattr(universe_module.os, "link", collide_links)
    monkeypatch.setattr(universe_module, "_read_regular_file", deny_sentinel_read)

    def publish(at: datetime) -> bool:
        try:
            _publish(tmp_path, at, True, None)
        except ConcurrentUniverseUpdateError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(publish, T1)
        second = executor.submit(publish, T2)
        assert first.result(timeout=20) != second.result(timeout=20)
    assert load_current_universe_state(tmp_path).ready
