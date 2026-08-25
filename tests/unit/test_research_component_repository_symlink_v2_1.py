from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from alpha_cycle.research_component_repository_v2_1 import (
    ResearchComponentRepositoryError,
    build_research_component_repository_index,
)


def test_snapshot_directory_symlink_is_rejected_before_payload_read(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "payoff_surface"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (repository / "20260823T090000000000Z__aaaaaaaaaaaa").symlink_to(
        outside,
        target_is_directory=True,
    )

    with pytest.raises(
        ResearchComponentRepositoryError,
        match="snapshot directory cannot be a symlink",
    ):
        build_research_component_repository_index(
            tmp_path,
            as_of=datetime(2026, 8, 23, 9, 0, tzinfo=UTC),
        )
