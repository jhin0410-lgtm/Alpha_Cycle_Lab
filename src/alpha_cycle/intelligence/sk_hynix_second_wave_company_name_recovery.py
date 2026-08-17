"""Recover legacy SK hynix company profitability by exact statement account names.

OpenDART taxonomy account IDs changed across older filings. This recovery is intentionally
narrow: it runs only on a preserved single-account-all payload, accepts exact Korean account
names in consolidated income statements, requires one semantic amount per account, binds all
three accounts to the same filing revision, and enforces Revenue - Cost of Sales = Gross
Profit. It does not infer fuzzy names, derive missing values, certify historical vintage, or
promote model rows.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_acquisition import (
    SecondWaveCompanyObservation,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    SecondWaveCandidate,
)

_ALLOWED_STATEMENTS = frozenset({"IS", "CIS"})
_ACCOUNT_NAMES = {
    "revenue": frozenset({"매출액", "수익(매출액)"}),
    "cost_of_sales": frozenset({"매출원가"}),
    "gross_profit": frozenset({"매출총이익"}),
}


def _norm(value: object) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split()).casefold()


def _object(path: Path) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Second-wave company raw payload not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Second-wave company raw payload is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Second-wave company raw payload must be an object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _financial_rows(payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    financials = payload.get("financials")
    if not isinstance(financials, dict):
        raise ValueError("Second-wave company raw payload lacks financials")
    raw_rows = cast(dict[object, object], financials).get("list")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("Second-wave company financial list must be non-empty")
    rows: list[dict[str, object]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise ValueError("Second-wave company financial row must be an object")
        rows.append(
            {str(key): value for key, value in cast(dict[object, object], raw_row).items()}
        )
    return tuple(rows)


def _integral_krw(value: object, label: str) -> int:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        raise ValueError(f"Second-wave company {label} is missing")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Second-wave company {label} is not numeric") from exc
    if negative:
        amount = -amount
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"Second-wave company {label} must be integral KRW")
    return int(amount)


@dataclass(frozen=True)
class ExactNameAccountSelection:
    label: str
    account_name: str
    account_ids: tuple[str, ...]
    amount_krw: int
    rcept_no: str
    available_date: date
    selection_basis: str = "exact_account_name"

    def __post_init__(self) -> None:
        if self.label not in _ACCOUNT_NAMES:
            raise ValueError("Second-wave account selection label is unsupported")
        if _norm(self.account_name) not in {_norm(item) for item in _ACCOUNT_NAMES[self.label]}:
            raise ValueError("Second-wave account selection used an unregistered exact name")
        if not self.account_ids:
            raise ValueError("Second-wave account selection must retain observed account IDs")
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Second-wave account selection receipt is invalid")
        if self.selection_basis != "exact_account_name":
            raise ValueError("Second-wave account selection basis drifted")


@dataclass(frozen=True)
class SecondWaveCompanyNameRecovery:
    period_id: str
    raw_payload_path: str
    raw_payload_sha256: str
    revenue_selection: ExactNameAccountSelection
    cost_of_sales_selection: ExactNameAccountSelection
    gross_profit_selection: ExactNameAccountSelection
    observation: SecondWaveCompanyObservation
    exact_name_only: bool = True
    accounting_identity_verified: bool = True
    training_row_promoted: bool = False
    fit_enabled: bool = False
    holdout_evaluation_allowed: bool = False

    def __post_init__(self) -> None:
        if len(self.raw_payload_sha256) != 64:
            raise ValueError("Second-wave company recovery hash must be SHA-256")
        if self.observation.period_id != self.period_id:
            raise ValueError("Second-wave company recovery period mismatch")
        receipts = {
            self.revenue_selection.rcept_no,
            self.cost_of_sales_selection.rcept_no,
            self.gross_profit_selection.rcept_no,
            self.observation.rcept_no,
        }
        if len(receipts) != 1:
            raise ValueError("Second-wave company recovery crossed filing revisions")
        if not self.exact_name_only or not self.accounting_identity_verified:
            raise ValueError("Second-wave company recovery trust checks are incomplete")
        if self.training_row_promoted or self.fit_enabled or self.holdout_evaluation_allowed:
            raise ValueError("Second-wave company recovery exceeded source trust boundary")


def _select_exact_name_account(
    rows: tuple[dict[str, object], ...],
    candidate: SecondWaveCandidate,
    *,
    label: str,
) -> ExactNameAccountSelection:
    allowed_names = {_norm(item) for item in _ACCOUNT_NAMES[label]}
    raw_matches: list[tuple[int, str, date, str, str]] = []
    for row in rows:
        if str(row.get("sj_div", "")).strip() not in _ALLOWED_STATEMENTS:
            continue
        account_name = str(row.get("account_nm", "")).strip()
        if _norm(account_name) not in allowed_names:
            continue
        row_year = str(row.get("bsns_year", "")).strip()
        row_code = str(row.get("reprt_code", "")).strip()
        if row_year and row_year != str(candidate.period_end.year):
            continue
        if row_code and row_code != candidate.company_profitability_report_code:
            continue
        receipt = str(row.get("rcept_no", "")).strip()
        if len(receipt) != 14 or not receipt.isdigit():
            raise ValueError(f"Second-wave company {label} receipt is invalid")
        available_date = date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8]))
        account_id = str(row.get("account_id", "")).strip()
        if not account_id:
            raise ValueError(f"Second-wave company {label} account ID is missing")
        raw_matches.append(
            (
                _integral_krw(row.get("thstrm_amount"), label),
                receipt,
                available_date,
                account_name,
                account_id,
            )
        )

    semantic = {(amount, receipt, available, _norm(name)) for amount, receipt, available, name, _ in raw_matches}
    if len(semantic) != 1:
        observed_names = tuple(sorted({name for _, _, _, name, _ in raw_matches}))
        raise ValueError(
            "Second-wave company exact-name account must resolve uniquely: "
            f"{candidate.period_id} {label} count={len(semantic)} names={observed_names}"
        )
    amount, receipt, available, normalized_name = next(iter(semantic))
    matching_rows = [item for item in raw_matches if _norm(item[3]) == normalized_name]
    account_ids = tuple(sorted({item[4] for item in matching_rows}))
    original_names = tuple(sorted({item[3] for item in matching_rows}))
    if len(original_names) != 1:
        raise ValueError(f"Second-wave company {label} exact-name spelling is ambiguous")
    return ExactNameAccountSelection(
        label=label,
        account_name=original_names[0],
        account_ids=account_ids,
        amount_krw=amount,
        rcept_no=receipt,
        available_date=available,
    )


def recover_second_wave_company_by_exact_names(
    candidate: SecondWaveCandidate,
    raw_payload_path: str | Path,
    *,
    evaluation_date: date,
) -> SecondWaveCompanyNameRecovery:
    """Recover one legacy company-profitability observation without fuzzy taxonomy matching."""

    path = Path(raw_payload_path)
    payload = _object(path)
    rows = _financial_rows(payload)
    revenue = _select_exact_name_account(rows, candidate, label="revenue")
    cost = _select_exact_name_account(rows, candidate, label="cost_of_sales")
    gross = _select_exact_name_account(rows, candidate, label="gross_profit")
    receipts = {revenue.rcept_no, cost.rcept_no, gross.rcept_no}
    dates = {revenue.available_date, cost.available_date, gross.available_date}
    if len(receipts) != 1 or len(dates) != 1:
        raise ValueError("Second-wave company exact-name accounts cross filing revisions")
    available_date = revenue.available_date
    if available_date > evaluation_date:
        raise ValueError("Second-wave company exact-name recovery uses future filing data")
    if revenue.amount_krw - cost.amount_krw != gross.amount_krw:
        raise ValueError("Second-wave company exact-name accounting identity failed")
    raw_bytes = path.read_bytes()
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    observation = SecondWaveCompanyObservation(
        period_id=candidate.period_id,
        rcept_no=revenue.rcept_no,
        available_date=available_date,
        revenue_krw=revenue.amount_krw,
        cost_of_sales_krw=cost.amount_krw,
        gross_profit_krw=gross.amount_krw,
        gross_margin_percent=gross.amount_krw / revenue.amount_krw * 100.0,
        raw_payload_sha256=raw_hash,
    )
    return SecondWaveCompanyNameRecovery(
        period_id=candidate.period_id,
        raw_payload_path=str(path.resolve()),
        raw_payload_sha256=raw_hash,
        revenue_selection=revenue,
        cost_of_sales_selection=cost,
        gross_profit_selection=gross,
        observation=observation,
    )


__all__ = [
    "ExactNameAccountSelection",
    "SecondWaveCompanyNameRecovery",
    "recover_second_wave_company_by_exact_names",
]
