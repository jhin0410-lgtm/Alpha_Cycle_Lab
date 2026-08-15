"""Certify only the period-column semantics of the SK hynix 2Q26 product-share chart.

The official 2Q26 PDF geometry proves three product-share columns.  This module pins the
exact source shape and certifies that the rightmost column corresponds to ``'26 Q2`` and
contains the raw percentage tokens ``73%`` and ``27%``.  It intentionally does not assign
those tokens to DRAM/NAND and does not infer ``Other=0``.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_product_geometry as geometry
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_geometry_verifier import (
    load_q2_product_geometry,
)

DEFAULT_Q2_SHARE_COLUMN_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-q2-share-column-certification"
)
DEFAULT_Q2_SHARE_COLUMN_POINTER = (
    DEFAULT_Q2_SHARE_COLUMN_OUTPUT / "latest_skhynix_ir_q2_share_column_certification.json"
)

_QUARTER_LABELS = ("'25 Q2", "'26 Q1", "'26 Q2")
_EXPECTED_COLUMN_TOKENS = (
    ("77%", "21%"),
    ("78%", "21%"),
    ("73%", "27%"),
)
_EXPECTED_CURRENT_PERIOD = "'26 Q2"
_EXPECTED_CURRENT_TOKENS = ("73%", "27%")
_REQUIRED_LEGEND_LABELS = ("DRAM", "NAND", "Others")
_REQUIRED_FOOTNOTE = "Revenue by product portion is based on KRW, Solidigm results consolidated"
_X_CLUSTER_TOLERANCE = 5.0
_SPACING_RELATIVE_TOLERANCE = 0.10
_PERCENTAGE = re.compile(r"^(?P<value>\d{1,3}(?:\.\d+)?)\s*%$")
_REQUIRED_FALSE_FLAGS = (
    "product_assignment_certified",
    "other_zero_certified",
    "numeric_semantics_certified",
    "registry_write_eligible",
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)


@dataclass(frozen=True)
class ShareColumnEvidence:
    period_label: str
    x_center: float
    percentage_tokens: tuple[str, ...]
    percentage_sum: float


@dataclass(frozen=True)
class OfficialIrQ2ShareColumnCertification:
    evidence_id: str
    geometry_evidence_id: str
    source_certification_evidence_id: str
    observed_date: date
    source_url: str
    pdf_sha256: str
    page_number: int
    quarter_labels: tuple[str, ...]
    columns: tuple[ShareColumnEvidence, ...]
    current_period_label: str
    current_period_start: str
    current_period_end: str
    current_column_percentage_tokens: tuple[str, ...]
    current_column_percentage_sum: float
    product_legend_labels: tuple[str, ...]
    footnote_verified: bool
    period_column_semantics_certified: bool
    product_assignment_certified: bool = False
    other_zero_certified: bool = False
    numeric_semantics_certified: bool = False
    registry_write_eligible: bool = False
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("SK hynix Q2 share-column evidence ID must be SHA-256")
        if not _valid_sha(self.geometry_evidence_id):
            raise ValueError("SK hynix Q2 share-column geometry ID must be SHA-256")
        if not _valid_sha(self.source_certification_evidence_id):
            raise ValueError("SK hynix Q2 share-column source certification ID must be SHA-256")
        if not _valid_sha(self.pdf_sha256):
            raise ValueError("SK hynix Q2 share-column PDF hash must be SHA-256")
        if not self.period_column_semantics_certified:
            raise ValueError("SK hynix Q2 share-column artifact must certify period columns")
        if any(getattr(self, flag) for flag in _REQUIRED_FALSE_FLAGS):
            raise ValueError("SK hynix Q2 share-column certification widened model trust")


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha_payload(payload: object) -> str:
    import hashlib

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("’", "'").replace("‘", "'").split())


def _percent_value(token: str) -> float:
    match = _PERCENTAGE.fullmatch(token.strip())
    if match is None:
        raise ValueError(f"invalid SK hynix share token: {token}")
    return float(match.group("value"))


def _column_payload(item: ShareColumnEvidence) -> dict[str, object]:
    return {
        "period_label": item.period_label,
        "x_center": item.x_center,
        "percentage_tokens": list(item.percentage_tokens),
        "percentage_sum": item.percentage_sum,
    }


def _certification_payload(item: OfficialIrQ2ShareColumnCertification) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_q2_share_column_certified",
        "evidence_id": item.evidence_id,
        "geometry_evidence_id": item.geometry_evidence_id,
        "source_certification_evidence_id": item.source_certification_evidence_id,
        "observed_date": item.observed_date.isoformat(),
        "source_url": item.source_url,
        "pdf_sha256": item.pdf_sha256,
        "page_number": item.page_number,
        "quarter_labels": list(item.quarter_labels),
        "columns": [_column_payload(value) for value in item.columns],
        "current_period_label": item.current_period_label,
        "current_period_start": item.current_period_start,
        "current_period_end": item.current_period_end,
        "current_column_percentage_tokens": list(item.current_column_percentage_tokens),
        "current_column_percentage_sum": item.current_column_percentage_sum,
        "product_legend_labels": list(item.product_legend_labels),
        "footnote_verified": item.footnote_verified,
        "period_column_semantics_certified": item.period_column_semantics_certified,
        "product_assignment_certified": False,
        "other_zero_certified": False,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def _product_page(item: geometry.OfficialIrQ2ProductGeometry) -> geometry.ProductGeometryPage:
    if item.readiness_status != "geometry_ready_for_semantic_review":
        raise ValueError("SK hynix Q2 geometry is not ready for share-column review")
    if len(item.pages) != 1:
        raise ValueError("SK hynix Q2 share-column contract requires exactly one product page")
    return item.pages[0]


def _quarter_label_fragment(page: geometry.ProductGeometryPage) -> geometry.TextFragment:
    midpoint = page.width / 2.0
    matches: list[geometry.TextFragment] = []
    for fragment in page.focus_fragments:
        if fragment.text_x >= midpoint:
            continue
        normalized = _normalize_text(fragment.text)
        positions = [normalized.find(label) for label in _QUARTER_LABELS]
        if all(position >= 0 for position in positions) and positions == sorted(positions):
            matches.append(fragment)
    if len(matches) != 1:
        raise ValueError("SK hynix product chart quarter-label sequence is not uniquely verified")
    return matches[0]


def _legend_labels(page: geometry.ProductGeometryPage) -> tuple[str, ...]:
    midpoint = page.width / 2.0
    present = {
        _normalize_text(fragment.text)
        for fragment in page.focus_fragments
        if fragment.text_x < midpoint
    }
    if not all(label in present for label in _REQUIRED_LEGEND_LABELS):
        raise ValueError("SK hynix product chart DRAM/NAND/Others legend is incomplete")
    return _REQUIRED_LEGEND_LABELS


def _verify_footnote(page: geometry.ProductGeometryPage) -> bool:
    normalized = " ".join(_normalize_text(item.text) for item in page.fragments)
    if _REQUIRED_FOOTNOTE not in normalized:
        raise ValueError("SK hynix product-share KRW/Solidigm footnote is missing")
    return True


def _cluster_percentages(
    page: geometry.ProductGeometryPage,
) -> tuple[tuple[geometry.TextFragment, ...], ...]:
    midpoint = page.width / 2.0
    fragments = [
        item
        for item in page.focus_fragments
        if item.text_x < midpoint and _PERCENTAGE.fullmatch(item.text.strip()) is not None
    ]
    if len(fragments) != 6:
        raise ValueError("SK hynix product chart must expose exactly six product-share tokens")
    fragments.sort(key=lambda item: item.text_x)

    clusters: list[list[geometry.TextFragment]] = []
    for fragment in fragments:
        if not clusters:
            clusters.append([fragment])
            continue
        center = sum(item.text_x for item in clusters[-1]) / len(clusters[-1])
        if abs(fragment.text_x - center) <= _X_CLUSTER_TOLERANCE:
            clusters[-1].append(fragment)
        else:
            clusters.append([fragment])
    if len(clusters) != 3 or any(len(cluster) != 2 for cluster in clusters):
        raise ValueError("SK hynix product share tokens do not form three two-token columns")

    centers = [sum(item.text_x for item in cluster) / len(cluster) for cluster in clusters]
    spacings = [centers[1] - centers[0], centers[2] - centers[1]]
    if min(spacings) <= 0:
        raise ValueError("SK hynix product share columns are not left-to-right")
    relative_delta = abs(spacings[0] - spacings[1]) / max(spacings)
    if relative_delta > _SPACING_RELATIVE_TOLERANCE:
        raise ValueError("SK hynix product share column spacing drifted from the source chart")
    return tuple(tuple(sorted(cluster, key=lambda item: item.text_y)) for cluster in clusters)


def build_q2_share_column_certification(
    item: geometry.OfficialIrQ2ProductGeometry,
) -> OfficialIrQ2ShareColumnCertification:
    page = _product_page(item)
    _quarter_label_fragment(page)
    legend_labels = _legend_labels(page)
    footnote_verified = _verify_footnote(page)
    raw_clusters = _cluster_percentages(page)

    columns: list[ShareColumnEvidence] = []
    for period_label, cluster, expected_tokens in zip(
        _QUARTER_LABELS,
        raw_clusters,
        _EXPECTED_COLUMN_TOKENS,
        strict=True,
    ):
        tokens = tuple(fragment.text.strip() for fragment in cluster)
        if tokens != expected_tokens:
            raise ValueError(
                f"SK hynix {period_label} product-share tokens drifted: {tokens}"
            )
        center = sum(fragment.text_x for fragment in cluster) / len(cluster)
        percentage_sum = round(sum(_percent_value(token) for token in tokens), 6)
        columns.append(
            ShareColumnEvidence(
                period_label=period_label,
                x_center=round(center, 6),
                percentage_tokens=tokens,
                percentage_sum=percentage_sum,
            )
        )

    current = columns[-1]
    if current.period_label != _EXPECTED_CURRENT_PERIOD:
        raise ValueError("SK hynix rightmost product-share column is not the expected 2Q26 period")
    if current.percentage_tokens != _EXPECTED_CURRENT_TOKENS:
        raise ValueError("SK hynix 2Q26 product-share column is not the expected 73%/27% pair")
    if current.percentage_sum != 100.0:
        raise ValueError("SK hynix 2Q26 product-share tokens do not sum to 100%")

    provisional = {
        "geometry_evidence_id": item.evidence_id,
        "source_certification_evidence_id": item.source_certification_evidence_id,
        "observed_date": item.observed_date.isoformat(),
        "source_url": item.source_url,
        "pdf_sha256": item.pdf_sha256,
        "page_number": page.page_number,
        "quarter_labels": list(_QUARTER_LABELS),
        "columns": [_column_payload(value) for value in columns],
        "current_period_label": _EXPECTED_CURRENT_PERIOD,
        "current_period_start": "2026-04-01",
        "current_period_end": "2026-06-30",
        "current_column_percentage_tokens": list(current.percentage_tokens),
        "current_column_percentage_sum": current.percentage_sum,
        "product_legend_labels": list(legend_labels),
        "footnote_verified": footnote_verified,
        "period_column_semantics_certified": True,
        "product_assignment_certified": False,
        "other_zero_certified": False,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrQ2ShareColumnCertification(
        evidence_id=_sha_payload(provisional),
        geometry_evidence_id=item.evidence_id,
        source_certification_evidence_id=item.source_certification_evidence_id,
        observed_date=item.observed_date,
        source_url=item.source_url,
        pdf_sha256=item.pdf_sha256,
        page_number=page.page_number,
        quarter_labels=_QUARTER_LABELS,
        columns=tuple(columns),
        current_period_label=_EXPECTED_CURRENT_PERIOD,
        current_period_start="2026-04-01",
        current_period_end="2026-06-30",
        current_column_percentage_tokens=current.percentage_tokens,
        current_column_percentage_sum=current.percentage_sum,
        product_legend_labels=legend_labels,
        footnote_verified=footnote_verified,
        period_column_semantics_certified=True,
    )


def capture_q2_share_column_certification(
    geometry_pointer_path: str | Path = geometry.DEFAULT_Q2_PRODUCT_GEOMETRY_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_Q2_SHARE_COLUMN_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    pointer_path = Path(geometry_pointer_path)
    geometry_item = load_q2_product_geometry(
        pointer_path,
        evaluation_date=evaluation_date,
    )
    certification = build_q2_share_column_certification(geometry_item)

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + certification.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("SK hynix Q2 share-column artifact path already exists")
    temporary.mkdir()
    try:
        report_path = temporary / "share_column_certification.json"
        report_path.write_text(
            json.dumps(
                _certification_payload(certification),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer_payload = {
        **_certification_payload(certification),
        "geometry_pointer_path": str(pointer_path.resolve()),
        "artifact_directory": str(directory.resolve()),
        "report_path": str((directory / "share_column_certification.json").resolve()),
    }
    temporary_pointer = root / ".latest_skhynix_ir_q2_share_column_certification.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(root / DEFAULT_Q2_SHARE_COLUMN_POINTER.name)
    return pointer_payload


__all__ = [
    "DEFAULT_Q2_SHARE_COLUMN_OUTPUT",
    "DEFAULT_Q2_SHARE_COLUMN_POINTER",
    "OfficialIrQ2ShareColumnCertification",
    "ShareColumnEvidence",
    "build_q2_share_column_certification",
    "capture_q2_share_column_certification",
]
