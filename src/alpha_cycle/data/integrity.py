"""Price-basis, corporate-action, and point-in-time universe contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from alpha_cycle.calendar.base import TradingCalendar


class PriceBasis(StrEnum):
    """Supported interpretations of market prices."""

    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN_ADJUSTED = "total_return_adjusted"


class CorporateActionType(StrEnum):
    """Corporate actions represented by the integrity layer."""

    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    CASH_DIVIDEND = "cash_dividend"
    STOCK_DIVIDEND = "stock_dividend"
    DELISTING = "delisting"


CORPORATE_ACTION_REQUIRED = (
    "ticker",
    "action_type",
    "effective_date",
    "available_date",
    "source",
    "revision_id",
)
CORPORATE_ACTION_OPTIONAL = (
    "ratio",
    "cash_amount",
    "currency",
    "record_date",
    "pay_date",
)
UNIVERSE_REQUIRED = (
    "universe",
    "ticker",
    "member_from",
    "member_to",
    "available_date",
    "source",
    "revision_id",
)


@dataclass(frozen=True)
class CorporateAction:
    """Immutable, validated corporate-action event."""

    ticker: str
    action_type: CorporateActionType
    effective_date: date
    available_date: date
    source: str
    revision_id: str
    ratio: Decimal | None = None
    cash_amount: Decimal | None = None
    currency: str | None = None
    record_date: date | None = None
    pay_date: date | None = None

    @property
    def event_key(self) -> tuple[str, CorporateActionType, date, str]:
        """Return a deterministic identifier for duplicate-application protection."""
        return (self.ticker, self.action_type, self.effective_date, self.revision_id)


def _required_text(data: pd.DataFrame, column: str) -> None:
    values = data[column].astype(str).str.strip()
    if values.eq("").any():
        raise ValueError(f"{column} cannot be empty")
    data[column] = values


def _optional_decimal(value: Any) -> Decimal | None:
    if pd.isna(value):
        return None
    return Decimal(str(value))


def _optional_date(value: Any) -> date | None:
    if pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="raise")
    return parsed.date()


def validate_corporate_actions(
    frame: pd.DataFrame,
    *,
    calendar: TradingCalendar | None = None,
) -> pd.DataFrame:
    """Validate corporate actions and return a deterministic canonical frame."""
    missing = sorted(set(CORPORATE_ACTION_REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing corporate-action columns: {', '.join(missing)}")
    data = frame.copy()
    for column in CORPORATE_ACTION_OPTIONAL:
        if column not in data.columns:
            data[column] = pd.NA
    if data.empty:
        return data.loc[:, [*CORPORATE_ACTION_REQUIRED, *CORPORATE_ACTION_OPTIONAL]]
    for column in ("ticker", "source", "revision_id"):
        _required_text(data, column)
    for column in ("effective_date", "available_date", "record_date", "pay_date"):
        data[column] = pd.to_datetime(data[column], errors="raise").dt.date
    try:
        data["action_type"] = data["action_type"].map(
            lambda value: CorporateActionType(str(value)).value
        )
    except ValueError as exc:
        raise ValueError(f"Unsupported corporate action type: {exc}") from exc
    if (data["available_date"] > data["effective_date"]).any():
        raise ValueError("available_date cannot follow effective_date in strict mode")
    duplicate_key = ["ticker", "action_type", "effective_date"]
    if data.duplicated(duplicate_key).any():
        raise ValueError("Duplicate corporate-action event detected")
    for row in data.itertuples(index=False):
        action_type = CorporateActionType(str(row.action_type))
        ratio = _optional_decimal(row.ratio)
        cash_amount = _optional_decimal(row.cash_amount)
        currency = None if pd.isna(row.currency) else str(row.currency).strip()
        if action_type in {
            CorporateActionType.SPLIT,
            CorporateActionType.REVERSE_SPLIT,
        }:
            if ratio is None or ratio <= 0 or ratio == 1:
                raise ValueError("Split ratio must be positive and different from 1")
            if cash_amount is not None:
                raise ValueError("Split events cannot define cash_amount")
        elif action_type is CorporateActionType.CASH_DIVIDEND:
            if cash_amount is None or cash_amount < 0:
                raise ValueError("Cash dividends require a non-negative cash_amount")
            if not currency:
                raise ValueError("Cash dividends require currency")
            if ratio is not None:
                raise ValueError("Cash dividends cannot define ratio")
        elif action_type is CorporateActionType.STOCK_DIVIDEND:
            if ratio is None or ratio <= 0:
                raise ValueError("Stock dividends require a positive ratio")
        if row.record_date is not None and row.pay_date is not None:
            if row.pay_date < row.record_date:
                raise ValueError("pay_date cannot precede record_date")
        if calendar is not None and not calendar.is_session(row.effective_date):
            raise ValueError(
                f"Corporate action effective date is not a trading session: "
                f"{row.effective_date}"
            )
    return data.sort_values(
        ["effective_date", "ticker", "action_type", "revision_id"],
        kind="stable",
    ).reset_index(drop=True)


class CorporateActionStore:
    """Point-in-time access to validated corporate actions."""

    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        calendar: TradingCalendar | None = None,
    ) -> None:
        self._data = validate_corporate_actions(frame, calendar=calendar)

    def as_of(self, information_date: date) -> pd.DataFrame:
        """Return events known by the supplied information date."""
        return self._data.loc[self._data["available_date"] <= information_date].copy()

    def actions_effective_on(
        self,
        session: date,
        *,
        information_date: date,
    ) -> list[CorporateAction]:
        """Return known actions effective on one trading session."""
        rows = self.as_of(information_date)
        rows = rows.loc[rows["effective_date"] == session]
        return [self._to_action(row) for _, row in rows.iterrows()]

    def actions_for_ticker(
        self,
        ticker: str,
        *,
        information_date: date,
    ) -> list[CorporateAction]:
        """Return known actions for one ticker in deterministic order."""
        rows = self.as_of(information_date)
        rows = rows.loc[rows["ticker"] == ticker]
        return [self._to_action(row) for _, row in rows.iterrows()]

    @staticmethod
    def _to_action(row: pd.Series[Any]) -> CorporateAction:
        return CorporateAction(
            ticker=str(row["ticker"]),
            action_type=CorporateActionType(str(row["action_type"])),
            effective_date=row["effective_date"],
            available_date=row["available_date"],
            source=str(row["source"]),
            revision_id=str(row["revision_id"]),
            ratio=_optional_decimal(row["ratio"]),
            cash_amount=_optional_decimal(row["cash_amount"]),
            currency=None if pd.isna(row["currency"]) else str(row["currency"]),
            record_date=_optional_date(row["record_date"]),
            pay_date=_optional_date(row["pay_date"]),
        )


def validate_universe_membership(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate point-in-time universe membership intervals."""
    missing = sorted(set(UNIVERSE_REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing universe columns: {', '.join(missing)}")
    data = frame.copy()
    if data.empty:
        return data.loc[:, list(UNIVERSE_REQUIRED)]
    for column in ("universe", "ticker", "source", "revision_id"):
        _required_text(data, column)
    for column in ("member_from", "member_to", "available_date"):
        data[column] = pd.to_datetime(data[column], errors="raise").dt.date
    invalid_end = data["member_to"].notna() & (
        data["member_to"] <= data["member_from"]
    )
    if invalid_end.any():
        raise ValueError("member_to must be later than member_from")
    if (data["available_date"] > data["member_from"]).any():
        raise ValueError("available_date cannot follow member_from in strict mode")
    ordered = data.sort_values(
        ["universe", "ticker", "member_from", "member_to"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    for (_, _), group in ordered.groupby(["universe", "ticker"], sort=True):
        previous_end: date | None = None
        for row in group.itertuples(index=False):
            if previous_end is None and row.Index if False else False:
                pass
            if previous_end is not None and row.member_from < previous_end:
                raise ValueError("Overlapping universe membership intervals detected")
            if previous_end is None and len(group) > 1:
                first = group.iloc[0]
                if pd.isna(first["member_to"]):
                    raise ValueError("Open-ended membership cannot be followed by another interval")
            previous_end = row.member_to
    return ordered


class UniverseMembershipStore:
    """Point-in-time access to historical universe membership."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._data = validate_universe_membership(frame)

    def members_as_of(
        self,
        universe: str,
        session: date,
        *,
        information_date: date | None = None,
    ) -> tuple[str, ...]:
        """Return members active on session and known by information_date."""
        known_on = information_date or session
        rows = self._data.loc[
            (self._data["universe"] == universe)
            & (self._data["available_date"] <= known_on)
            & (self._data["member_from"] <= session)
            & (
                self._data["member_to"].isna()
                | (session < self._data["member_to"])
            )
        ]
        return tuple(sorted(rows["ticker"].astype(str).unique()))

    def is_member(
        self,
        universe: str,
        ticker: str,
        session: date,
        *,
        information_date: date | None = None,
    ) -> bool:
        """Return whether ticker is an active, known member on session."""
        return ticker in self.members_as_of(
            universe,
            session,
            information_date=information_date,
        )
