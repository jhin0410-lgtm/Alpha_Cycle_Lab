"""Resolve correction parents from explicit OpenDART body target metadata."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date

_TARGET_DATE = re.compile(
    r"(?:\b2\.\s*)?정정\s*관련\s*공시서류\s*제출일\s*"
    r"(?P<date>"
    r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일"
    r"|\d{4}[-./]\d{1,2}[-./]\d{1,2}"
    r")"
)


def _date_value(value: object) -> date | None:
    text = str(value).strip()
    if not text:
        return None
    numbers = re.findall(r"\d+", text)
    if len(numbers) != 3:
        return None
    try:
        return date(*(int(item) for item in numbers))
    except ValueError:
        return None


def correction_target_submission_date(text: object) -> date | None:
    """Return the explicitly stated target filing date from a correction body."""

    match = _TARGET_DATE.search(str(text))
    return _date_value(match.group("date")) if match is not None else None


def resolve_correction_parent_from_body(
    current_record: Mapping[str, object],
    document_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Resolve one exact parent candidate from body target date + ticker + family.

    The resolver never falls back to value matching. If the correction body states a
    target submission date, that date is treated as stronger provenance than the
    generic nearest-prior-filing heuristic. Ambiguity therefore fails closed.
    """

    current_receipt = str(current_record.get("rcept_no", "")).strip()
    ticker = str(current_record.get("ticker", "")).strip().zfill(6)
    family = str(current_record.get("correction_family_key", "")).strip()
    target_date = correction_target_submission_date(current_record.get("text", ""))
    if target_date is None:
        return {
            "status": "target_submission_date_not_found",
            "resolution_source": None,
            "target_submission_date": None,
            "parent_rcept_no": None,
        }

    current_date = _date_value(current_record.get("receipt_date"))
    if current_date is not None and target_date > current_date:
        return {
            "status": "target_submission_date_invalid",
            "resolution_source": "body_target_submission_date",
            "target_submission_date": target_date.isoformat(),
            "parent_rcept_no": None,
        }

    candidates: list[str] = []
    for key, raw_value in document_evidence.items():
        if not isinstance(raw_value, Mapping):
            continue
        receipt = str(raw_value.get("rcept_no", key)).strip()
        if receipt == current_receipt:
            continue
        candidate_ticker = str(raw_value.get("ticker", "")).strip().zfill(6)
        candidate_family = str(raw_value.get("correction_family_key", "")).strip()
        candidate_date = _date_value(raw_value.get("receipt_date"))
        if (
            candidate_ticker == ticker
            and candidate_family == family
            and candidate_date == target_date
        ):
            candidates.append(receipt)

    unique = sorted(set(candidates))
    if not unique:
        return {
            "status": "target_parent_not_found",
            "resolution_source": "body_target_submission_date",
            "target_submission_date": target_date.isoformat(),
            "parent_rcept_no": None,
        }
    if len(unique) != 1:
        return {
            "status": "target_parent_ambiguous",
            "resolution_source": "body_target_submission_date",
            "target_submission_date": target_date.isoformat(),
            "parent_rcept_no": None,
            "candidate_rcept_nos": unique,
        }
    return {
        "status": "resolved",
        "resolution_source": "body_target_submission_date",
        "target_submission_date": target_date.isoformat(),
        "parent_rcept_no": unique[0],
    }


__all__ = [
    "correction_target_submission_date",
    "resolve_correction_parent_from_body",
]
