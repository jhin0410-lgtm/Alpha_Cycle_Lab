"""Verify supported OpenDART correction deltas against current and parent bodies."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from alpha_cycle.intelligence.disclosure_body_metrics import (
    parse_disclosure_body_metrics,
)
from alpha_cycle.intelligence.disclosure_correction_parent import (
    resolve_correction_parent_from_body,
)
from alpha_cycle.intelligence.disclosure_grouped_correction import (
    parse_grouped_earnings_delta_rows,
)

CORRECTION_DELTA_SCHEMA_VERSION = 1
_NUMBER = r"(?:-?\d[\d,]*(?:\.\d+)?|-)"


def _valid_sha256(value: object) -> bool:
    text = str(value).strip().casefold()
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def _collected_body(record: Mapping[str, object] | None) -> bool:
    if record is None or record.get("status") != "collected":
        return False
    chars = record.get("text_chars")
    if isinstance(chars, bool) or not isinstance(chars, int) or chars <= 0:
        return False
    if record.get("text_truncated") is not False:
        return False
    return _valid_sha256(record.get("text_sha256")) and _valid_sha256(
        record.get("archive_sha256")
    )


def _canonical_number(value: str) -> str | None:
    text = value.strip().replace(",", "")
    if text == "-":
        return None
    try:
        numeric = Decimal(text)
    except InvalidOperation:
        return None
    return format(numeric, "f") if numeric.is_finite() else None


def _decimal_equal(left: object, right: object) -> bool:
    left_value = _canonical_number(str(left)) if left is not None else None
    right_value = _canonical_number(str(right)) if right is not None else None
    return left_value == right_value


def _integer_equal(left: object, right: object) -> bool:
    try:
        return int(str(left).replace(",", "")) == int(str(right).replace(",", ""))
    except ValueError:
        return False


def _correction_section(text: object, heading: re.Pattern[str]) -> str | None:
    body = str(text)
    marker = re.search(r"정정\s*항목\s+정정\s*전\s+정정\s*후", body)
    if marker is None:
        return None
    matches = [
        match for match in heading.finditer(body) if match.start() > marker.end()
    ]
    end = matches[-1].start() if matches else len(body)
    if end <= marker.end():
        return None
    return re.sub(r"\s+", " ", body[marker.end() : end]).strip()


def _rowwise_earnings_delta_rows(section: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    definitions = (
        ("sales", ("매출액(당해실적)", "매출액 당해실적")),
        ("operating_profit", ("영업이익(당해실적)", "영업이익 당해실적")),
        ("net_income", ("당기순이익(당해실적)", "당기순이익 당해실적")),
    )
    for field, labels in definitions:
        match: re.Match[str] | None = None
        for label in labels:
            match = re.search(
                rf"{re.escape(label)}\s+({_NUMBER})\s+({_NUMBER})",
                section,
            )
            if match is not None:
                break
        if match is None:
            continue
        before = _canonical_number(match.group(1))
        after = _canonical_number(match.group(2))
        rows.append(
            {
                "field": field,
                "before": before,
                "after": after,
                "changed": before != after,
            }
        )
    return rows


def _earnings_delta_rows(text: object) -> list[dict[str, object]]:
    heading = re.compile(
        r"연결\s*재무제표\s*기준\s*영업\s*\(잠정\)\s*실적\s*\(공정공시\)"
    )
    section = _correction_section(text, heading)
    if section is None:
        return []
    grouped = parse_grouped_earnings_delta_rows(section)
    if grouped:
        return grouped
    return _rowwise_earnings_delta_rows(section)


def _capex_delta_rows(text: object) -> list[dict[str, object]]:
    section = _correction_section(text, re.compile(r"신규\s*시설투자\s*등"))
    if section is None:
        return []
    rows: list[dict[str, object]] = []
    definitions = (
        ("investment_amount_krw", "투자금액(원)", "integer"),
        ("equity_ratio_pct", "자기자본대비(%)", "decimal"),
    )
    for field, label, value_type in definitions:
        match = re.search(
            rf"{re.escape(label)}\s+({_NUMBER})\s+({_NUMBER})",
            section,
        )
        if match is None:
            continue
        if value_type == "integer":
            before: object = int(match.group(1).replace(",", ""))
            after: object = int(match.group(2).replace(",", ""))
        else:
            before = _canonical_number(match.group(1))
            after = _canonical_number(match.group(2))
        rows.append(
            {
                "field": field,
                "before": before,
                "after": after,
                "changed": before != after,
            }
        )
    return rows


def _metric_value(metrics: Mapping[str, object], field: str) -> object:
    if str(metrics.get("type", "")) == "earnings_preliminary":
        rows = metrics.get("metrics")
        if not isinstance(rows, Mapping):
            return None
        row = rows.get(field)
        return row.get("current") if isinstance(row, Mapping) else None
    if str(metrics.get("type", "")) == "facility_investment":
        return metrics.get(field)
    return None


def _value_equal(metric_type: str, field: str, left: object, right: object) -> bool:
    if metric_type == "facility_investment" and field == "investment_amount_krw":
        return _integer_equal(left, right)
    return _decimal_equal(left, right)


def _parent_binding_valid(
    current_receipt: str,
    current_record: Mapping[str, object],
    parent_receipt: str,
    parent_record: Mapping[str, object],
) -> bool:
    if str(current_record.get("correction_parent_rcept_no", "")).strip() != parent_receipt:
        return False
    if str(current_record.get("ticker", "")).zfill(6) != str(
        parent_record.get("ticker", "")
    ).zfill(6):
        return False
    if str(current_record.get("correction_family_key", "")).strip() != str(
        parent_record.get("correction_family_key", "")
    ).strip():
        return False
    if str(current_record.get("correction_chain_root_rcept_no", "")).strip() != str(
        parent_record.get("correction_chain_root_rcept_no", "")
    ).strip():
        return False
    try:
        current_order = int(str(current_record.get("correction_chain_order", "")))
        parent_order = int(str(parent_record.get("correction_chain_order", "")))
    except ValueError:
        return False
    if parent_order != current_order - 1:
        return False
    supporters = parent_record.get("supports_selected_receipts")
    if not isinstance(supporters, list):
        return False
    return current_receipt in {str(value).strip() for value in supporters}


def _heuristic_parent_receipt(
    catalyst: Mapping[Any, object],
    current_record: Mapping[str, object],
) -> str:
    receipt = str(catalyst.get("correction_parent_rcept_no", "") or "").strip()
    if receipt:
        return receipt
    return str(current_record.get("correction_parent_rcept_no", "") or "").strip()


def _parent_resolution(
    catalyst: Mapping[Any, object],
    current_record: Mapping[str, object],
    document_evidence: Mapping[str, object],
) -> dict[str, object]:
    heuristic_parent = _heuristic_parent_receipt(catalyst, current_record)
    body_resolution = resolve_correction_parent_from_body(
        current_record,
        document_evidence,
    )
    body_status = str(body_resolution.get("status", ""))
    if body_status != "target_submission_date_not_found":
        result = dict(body_resolution)
        result["heuristic_parent_rcept_no"] = heuristic_parent or None
        return result
    return {
        "status": "resolved" if heuristic_parent else "parent_not_found",
        "resolution_source": "window_heuristic" if heuristic_parent else None,
        "target_submission_date": None,
        "parent_rcept_no": heuristic_parent or None,
        "heuristic_parent_rcept_no": heuristic_parent or None,
    }


def _resolution_failure(
    resolution: Mapping[str, object],
    metric_type: str,
) -> dict[str, object] | None:
    status = str(resolution.get("status", ""))
    status_map = {
        "target_submission_date_invalid": "parent_body_target_invalid",
        "target_parent_not_found": "parent_body_target_unresolved",
        "target_parent_ambiguous": "parent_body_target_ambiguous",
        "parent_not_found": "parent_body_unavailable",
    }
    mapped = status_map.get(status)
    if mapped is None:
        return None
    result: dict[str, object] = {
        "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
        "status": mapped,
        "metric_type": metric_type,
        "parent_rcept_no": resolution.get("parent_rcept_no"),
        "parent_resolution_source": resolution.get("resolution_source"),
        "parent_target_submission_date": resolution.get("target_submission_date"),
        "heuristic_parent_rcept_no": resolution.get("heuristic_parent_rcept_no"),
    }
    candidates = resolution.get("candidate_rcept_nos")
    if isinstance(candidates, list):
        result["candidate_rcept_nos"] = candidates
    return result


def verify_correction_delta(
    catalyst: Mapping[Any, object],
    current_record: Mapping[str, object],
    document_evidence: Mapping[str, object],
    *,
    current_metrics: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Verify supported before/after fields against current and parent filings."""

    current_receipt = str(catalyst.get("rcept_no", "")).strip()
    if not bool(catalyst.get("is_correction", False)):
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "not_correction",
        }
    if (
        not current_receipt
        or str(current_record.get("rcept_no", "")).strip() != current_receipt
    ):
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "current_receipt_binding_mismatch",
        }
    if not _collected_body(current_record):
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "current_body_unavailable",
        }

    metrics = (
        dict(current_metrics)
        if current_metrics is not None
        else parse_disclosure_body_metrics(
            current_record.get("report_name", catalyst.get("report_name", "")),
            current_record.get("text", ""),
        )
    )
    if metrics.get("status") != "verified":
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "current_metrics_unverified",
            "metric_type": metrics.get("type"),
        }
    metric_type = str(metrics.get("type", ""))
    if metric_type == "earnings_preliminary":
        rows = _earnings_delta_rows(current_record.get("text", ""))
    elif metric_type == "facility_investment":
        rows = _capex_delta_rows(current_record.get("text", ""))
    else:
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "unsupported_metric_type",
            "metric_type": metric_type,
        }
    if not rows:
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "supported_delta_fields_not_found",
            "metric_type": metric_type,
        }

    resolution = _parent_resolution(catalyst, current_record, document_evidence)
    failure = _resolution_failure(resolution, metric_type)
    if failure is not None:
        return failure

    parent_receipt = str(resolution.get("parent_rcept_no", "") or "").strip()
    parent_value = document_evidence.get(parent_receipt) if parent_receipt else None
    parent_record = parent_value if isinstance(parent_value, Mapping) else None
    if not parent_receipt or not _collected_body(parent_record):
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "parent_body_unavailable",
            "metric_type": metric_type,
            "parent_rcept_no": parent_receipt or None,
            "parent_resolution_source": resolution.get("resolution_source"),
            "parent_target_submission_date": resolution.get("target_submission_date"),
            "heuristic_parent_rcept_no": resolution.get("heuristic_parent_rcept_no"),
        }
    assert parent_record is not None

    resolution_source = str(resolution.get("resolution_source", ""))
    if resolution_source == "window_heuristic" and not _parent_binding_valid(
        current_receipt,
        current_record,
        parent_receipt,
        parent_record,
    ):
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "parent_lineage_binding_mismatch",
            "metric_type": metric_type,
            "parent_rcept_no": parent_receipt,
            "parent_resolution_source": resolution_source,
            "parent_target_submission_date": None,
            "heuristic_parent_rcept_no": resolution.get("heuristic_parent_rcept_no"),
        }
    if (
        resolution_source == "body_target_submission_date"
        and str(parent_record.get("rcept_no", "")).strip() != parent_receipt
    ):
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "parent_lineage_binding_mismatch",
            "metric_type": metric_type,
            "parent_rcept_no": parent_receipt,
            "parent_resolution_source": resolution_source,
            "parent_target_submission_date": resolution.get("target_submission_date"),
            "heuristic_parent_rcept_no": resolution.get("heuristic_parent_rcept_no"),
        }

    parent_metrics = parse_disclosure_body_metrics(
        parent_record.get("report_name", ""),
        parent_record.get("text", ""),
    )
    if (
        parent_metrics.get("status") != "verified"
        or str(parent_metrics.get("type", "")) != metric_type
    ):
        return {
            "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
            "status": "parent_metrics_unverified",
            "metric_type": metric_type,
            "parent_rcept_no": parent_receipt,
            "parent_resolution_source": resolution_source,
            "parent_target_submission_date": resolution.get("target_submission_date"),
            "heuristic_parent_rcept_no": resolution.get("heuristic_parent_rcept_no"),
        }

    verified_rows: list[dict[str, object]] = []
    mismatch = False
    changed_count = 0
    for row in rows:
        field = str(row["field"])
        before = row.get("before")
        after = row.get("after")
        current_value = _metric_value(metrics, field)
        parent_value = _metric_value(parent_metrics, field)
        after_matches = _value_equal(metric_type, field, after, current_value)
        before_matches = _value_equal(metric_type, field, before, parent_value)
        changed = bool(row.get("changed", False))
        changed_count += int(changed)
        mismatch = mismatch or not after_matches or not before_matches
        verified_rows.append(
            {
                "field": field,
                "before": before,
                "after": after,
                "parent_current": parent_value,
                "current_final": current_value,
                "changed": changed,
                "before_matches_parent": before_matches,
                "after_matches_current": after_matches,
            }
        )

    if mismatch:
        status = "value_mismatch"
    elif changed_count == 0:
        status = "no_supported_value_change"
    else:
        status = "verified"
    return {
        "schema_version": CORRECTION_DELTA_SCHEMA_VERSION,
        "status": status,
        "scope": "supported_fields_only",
        "metric_type": metric_type,
        "current_rcept_no": current_receipt,
        "parent_rcept_no": parent_receipt,
        "parent_resolution_source": resolution_source,
        "parent_target_submission_date": resolution.get("target_submission_date"),
        "heuristic_parent_rcept_no": resolution.get("heuristic_parent_rcept_no"),
        "current_text_sha256": str(current_record.get("text_sha256")),
        "current_archive_sha256": str(current_record.get("archive_sha256")),
        "parent_text_sha256": str(parent_record.get("text_sha256")),
        "parent_archive_sha256": str(parent_record.get("archive_sha256")),
        "verified_field_count": len(verified_rows),
        "changed_field_count": changed_count,
        "fields": verified_rows,
    }


__all__ = ["CORRECTION_DELTA_SCHEMA_VERSION", "verify_correction_delta"]
