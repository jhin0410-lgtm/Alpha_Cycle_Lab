"""Expected-value raw replay for SK hynix 2Q26 OpenDART product revenue.

OpenDART's original HTML/XML may interleave layout metadata and numeric tokens even when
its normalized text presents the product revenue row cleanly. This verifier therefore
keeps the normalized-text parser as the value-discovery path and uses the raw archive as
an independent representation check:

* strict table geometry must still certify one current consolidated
  DRAM/NAND/Other/Total product header and KRW unit;
* the four normalized current-quarter amounts must occur in canonical order after a raw
  revenue label near that product header sequence;
* one cumulative amount must exist between each adjacent current-quarter product amount,
  plus a cumulative total after the current-quarter total;
* those four cumulative amounts must independently reconcile.

No amount is inferred from a residual and no product profitability is introduced here.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
    _parse_amount,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_layout import (
    parse_periodic_product_revenue_text,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_semantic_replay import (
    _PRODUCT_KEYS,
    _REVENUE_LABELS,
    _TEXT_SUFFIXES,
    _accepted,
    _grid,
    _header_candidates,
    _header_product_order,
    _normalized,
    _SourceTokenExtractor,
    _structured_unit,
    _TableExtractor,
)
from alpha_cycle.providers.opendart_documents import (
    _decode_text,
    _parse_document_archive,
    _safe_member_name,
)

_HEADER_LOOKBACK_TOKENS = 800
_RAW_SCAN_TOKENS = 1600
_MAX_NUMERIC_VALUES = 192
_RECONCILIATION_TOLERANCE = 0.5


def _label_key(
    spec: PeriodicProductRevenueSpec,
    token: str,
) -> str | None:
    normalized = _normalized(token)
    label_sets = {
        "dram": _accepted(spec.product_labels["dram_total"]),
        "nand": _accepted(spec.product_labels["nand_and_solutions"]),
        "other": _accepted(spec.product_labels["other_products_services"]),
        "total": _accepted(spec.product_labels["reported_company_revenue"]),
    }
    matched = [
        key
        for key, labels in label_sets.items()
        if any(label and (normalized == label or label in normalized) for label in labels)
    ]
    if len(matched) == 1:
        return matched[0]
    return None


def _canonical_header_before(
    spec: PeriodicProductRevenueSpec,
    tokens: tuple[str, ...],
    *,
    position: int,
) -> bool:
    start = max(0, position - _HEADER_LOOKBACK_TOKENS)
    observed: list[str] = []
    for token in tokens[start:position]:
        key = _label_key(spec, token)
        if key is not None and (not observed or observed[-1] != key):
            observed.append(key)
    return any(
        tuple(observed[index : index + 4]) == _PRODUCT_KEYS
        for index in range(max(0, len(observed) - 3))
    )


def _numbers_after_revenue_label(
    tokens: tuple[str, ...],
    *,
    position: int,
) -> tuple[float, ...]:
    numeric: list[float] = []
    accepted_revenue = _accepted(_REVENUE_LABELS)
    for token in tokens[position + 1 : position + 1 + _RAW_SCAN_TOKENS]:
        normalized = _normalized(token)
        if numeric and normalized in accepted_revenue:
            break
        amount = _parse_amount(token)
        if amount is None:
            continue
        numeric.append(amount)
        if len(numeric) >= _MAX_NUMERIC_VALUES:
            break
    return tuple(numeric)


def _matches(value: float, expected: float, *, tolerance: float) -> bool:
    return abs(value - expected) <= tolerance


def _cumulative_reconciles_between_currents(
    numeric: tuple[float, ...],
    *,
    current_positions: tuple[int, int, int, int],
    tolerance: float,
) -> bool:
    dram_pos, nand_pos, other_pos, total_pos = current_positions
    dram_cumulative = numeric[dram_pos + 1 : nand_pos]
    nand_cumulative = numeric[nand_pos + 1 : other_pos]
    other_cumulative = numeric[other_pos + 1 : total_pos]
    total_cumulative = numeric[total_pos + 1 :]
    if not all((dram_cumulative, nand_cumulative, other_cumulative, total_cumulative)):
        return False

    for dram in dram_cumulative:
        for nand in nand_cumulative:
            subtotal = dram + nand
            for other in other_cumulative:
                target = subtotal + other
                if any(
                    abs(total - target) <= tolerance
                    for total in total_cumulative
                ):
                    return True
    return False


def _expected_current_sequence_present(
    numeric: tuple[float, ...],
    *,
    expected: ProductRevenueMetrics,
    scale: float,
) -> bool:
    expected_raw = (
        expected.dram_total / scale,
        expected.nand_and_solutions / scale,
        expected.other_products_services / scale,
        expected.reported_company_revenue / scale,
    )
    tolerance = max(1e-9, _RECONCILIATION_TOLERANCE / scale)
    positions = [
        tuple(
            index
            for index, value in enumerate(numeric)
            if _matches(value, target, tolerance=tolerance)
        )
        for target in expected_raw
    ]
    if any(not values for values in positions):
        return False

    for dram_pos in positions[0]:
        for nand_pos in positions[1]:
            if nand_pos <= dram_pos + 1:
                continue
            for other_pos in positions[2]:
                if other_pos <= nand_pos + 1:
                    continue
                for total_pos in positions[3]:
                    if total_pos <= other_pos + 1:
                        continue
                    if _cumulative_reconciles_between_currents(
                        numeric,
                        current_positions=(dram_pos, nand_pos, other_pos, total_pos),
                        tolerance=tolerance,
                    ):
                        return True
    return False


def _expected_from_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    document = _parse_document_archive(
        archive_bytes,
        receipt="offline-replay",
        retrieved_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    if document.text_truncated:
        raise ValueError("OpenDART expected-value replay refuses truncated normalized text")
    return parse_periodic_product_revenue_text(spec, document.text)


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Verify normalized product revenue against strict header and raw source tokens."""

    expected = _expected_from_archive(spec, archive_bytes)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("OpenDART expected-value replay source is not a ZIP") from exc

    structural_headers = 0
    raw_revenue_labels = 0
    validated_occurrences = 0
    accepted_revenue = _accepted(_REVENUE_LABELS)
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_name = _safe_member_name(info.filename)
            if PurePosixPath(safe_name).suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            decoded, _encoding = _decode_text(archive.read(info))

            table_parser = _TableExtractor()
            table_parser.feed(decoded)
            table_parser.close()
            headers = _header_candidates(spec, table_parser.tables)
            structural_headers += len(headers)
            if not headers:
                continue

            source_parser = _SourceTokenExtractor()
            source_parser.feed(decoded)
            source_parser.close()
            source_tokens = tuple(source_parser.tokens)
            raw_revenue_labels += sum(
                1 for token in source_tokens if _normalized(token) in accepted_revenue
            )

            for _header_index, header in headers:
                if _header_product_order(spec, header) != _PRODUCT_KEYS:
                    continue
                unit, scale = _structured_unit(header, _grid(header))
                if unit != expected.unit:
                    continue
                for position, token in enumerate(source_tokens):
                    if _normalized(token) not in accepted_revenue:
                        continue
                    if not _canonical_header_before(spec, source_tokens, position=position):
                        continue
                    numeric = _numbers_after_revenue_label(
                        source_tokens,
                        position=position,
                    )
                    if _expected_current_sequence_present(
                        numeric,
                        expected=expected,
                        scale=scale,
                    ):
                        validated_occurrences += 1

    if structural_headers != 1 or validated_occurrences < 1:
        raise ValueError(
            "OpenDART expected-value raw replay did not certify the normalized product revenue: "
            f"current_consolidated_headers={structural_headers} "
            f"raw_source_revenue_labels={raw_revenue_labels} "
            f"validated_occurrences={validated_occurrences} "
            f"expected={expected}"
        )
    return expected


__all__ = ["parse_periodic_product_revenue_archive"]
