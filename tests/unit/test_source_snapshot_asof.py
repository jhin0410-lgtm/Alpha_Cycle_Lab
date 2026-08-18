from datetime import date

import pytest

from alpha_cycle.intelligence.source_snapshot_asof import source_snapshot_date_as_of


def test_source_snapshot_allows_later_as_of_without_rewriting_snapshot_date() -> None:
    snapshot = source_snapshot_date_as_of(
        "2026-08-15",
        as_of_date=date(2026, 8, 18),
        label="Historical panel",
    )

    assert snapshot == date(2026, 8, 15)


def test_source_snapshot_allows_exact_as_of_date() -> None:
    snapshot = source_snapshot_date_as_of(
        "2026-08-18",
        as_of_date=date(2026, 8, 18),
        label="Historical panel",
    )

    assert snapshot == date(2026, 8, 18)


def test_source_snapshot_rejects_future_snapshot() -> None:
    with pytest.raises(ValueError, match="was not yet observable"):
        source_snapshot_date_as_of(
            "2026-08-19",
            as_of_date=date(2026, 8, 18),
            label="Historical panel",
        )


def test_source_snapshot_rejects_invalid_date() -> None:
    with pytest.raises(ValueError, match="evaluation date is invalid"):
        source_snapshot_date_as_of(
            "not-a-date",
            as_of_date=date(2026, 8, 18),
            label="Historical panel",
        )
