"""Shared as-of semantics for replaying immutable historical source snapshots."""

from __future__ import annotations

from datetime import date


def source_snapshot_date_as_of(
    source_evaluation_date_raw: object,
    *,
    as_of_date: date,
    label: str,
) -> date:
    """Return the frozen snapshot date when it was observable by ``as_of_date``.

    Historical evidence must be replayed at the date embedded in its own immutable
    snapshot so its evidence hash remains reproducible.  A later caller date is only an
    upper-bound visibility check; it must never be substituted into the historical hash.
    """

    try:
        source_evaluation_date = date.fromisoformat(str(source_evaluation_date_raw))
    except ValueError as exc:
        raise ValueError(f"{label} evaluation date is invalid") from exc
    if source_evaluation_date > as_of_date:
        raise ValueError(f"{label} was not yet observable")
    return source_evaluation_date


__all__ = ["source_snapshot_date_as_of"]
