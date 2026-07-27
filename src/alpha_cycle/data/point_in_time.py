"""Point-in-time data contract preventing premature observations."""

from __future__ import annotations

from datetime import date

import pandas as pd

PIT_REQUIRED = (
    "observation_date",
    "available_date",
    "retrieved_at",
    "source",
    "revision_id",
)


def validate_point_in_time(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate availability chronology and return a canonical frame."""
    missing = sorted(set(PIT_REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing PIT columns: {', '.join(missing)}")
    data = frame.copy()
    for column in ("observation_date", "available_date"):
        data[column] = pd.to_datetime(data[column], errors="raise").dt.date
    data["retrieved_at"] = pd.to_datetime(data["retrieved_at"], errors="raise", utc=True)
    if data[list(PIT_REQUIRED)].isna().any().any():
        raise ValueError("PIT required values cannot be missing")
    if (data["available_date"] < data["observation_date"]).any():
        raise ValueError("available_date cannot precede observation_date")
    return data.sort_values(["available_date", "observation_date"], kind="stable").reset_index(
        drop=True
    )


class PointInTimeStore:
    """Availability-gated access to versioned research data."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._data = validate_point_in_time(frame)

    def as_of(self, evaluation_date: date) -> pd.DataFrame:
        """Return rows whose release date is known by evaluation_date."""
        return self._data.loc[self._data["available_date"] <= evaluation_date].copy()

