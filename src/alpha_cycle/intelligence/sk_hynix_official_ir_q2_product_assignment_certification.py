"""Certify DRAM/NAND assignment for the SK hynix 2Q26 product-share chart.

This stage consumes the already verified share-column and product-geometry evidence, then
replays the archived official PDF vector content.  It binds legend swatch fill styles to the
current-quarter stacked-bar rectangles and verifies that the visible 73% token is inside the
DRAM-coloured segment while 27% is inside the NAND-coloured segment.

The chart also contains a positive-area Others-coloured segment without a numeric token.
That presence is preserved as evidence only.  No numeric Other share is inferred and
Other=0 is explicitly not certified.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import ContentStream

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_product_geometry as geometry
from alpha_cycle.intelligence import sk_hynix_official_ir_q2_share_column_certification as share
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_geometry_verifier import (
    load_q2_product_geometry,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_share_column_certification_verifier import (
    load_q2_share_column_certification,
)

DEFAULT_Q2_PRODUCT_ASSIGNMENT_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-q2-product-assignment-certification"
)
DEFAULT_Q2_PRODUCT_ASSIGNMENT_POINTER = (
    DEFAULT_Q2_PRODUCT_ASSIGNMENT_OUTPUT
    / "latest_skhynix_ir_q2_product_assignment_certification.json"
)

_CURRENT_PERIOD = "'26 Q2"
_EXPECTED_DRAM_TOKEN = "73%"
_EXPECTED_NAND_TOKEN = "27%"
_PRODUCTS = ("DRAM", "NAND", "Others")
_SMALL_SWATCH_MAX = 30.0
_SWATCH_VERTICAL_TOLERANCE = 15.0
_SWATCH_HORIZONTAL_GAP_MAX = 50.0
_SEGMENT_MIN_WIDTH = 50.0
_SEGMENT_TOKEN_TOLERANCE = 2.0
_SEGMENT_X_TOLERANCE = 2.0
_SEGMENT_CONTIGUITY_TOLERANCE = 1.0
_REQUIRED_FALSE_FLAGS = (
    "other_zero_certified",
    "numeric_semantics_certified",
    "registry_write_eligible",
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)


@dataclass(frozen=True)
class FillStyle:
    color_space: str
    components: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.color_space not in {"gray", "rgb"}:
            raise ValueError("SK hynix vector fill style has unsupported color space")
        expected = 1 if self.color_space == "gray" else 3
        if len(self.components) != expected:
            raise ValueError("SK hynix vector fill style component count is invalid")
        if any(value < 0.0 or value > 1.0 for value in self.components):
            raise ValueError("SK hynix vector fill style component is outside [0, 1]")


@dataclass(frozen=True)
class PaintedRectangle:
    x: float
    y: float
    width: float
    height: float
    fill: FillStyle

    @property
    def x_min(self) -> float:
        return min(self.x, self.x + self.width)

    @property
    def x_max(self) -> float:
        return max(self.x, self.x + self.width)

    @property
    def y_min(self) -> float:
        return min(self.y, self.y + self.height)

    @property
    def y_max(self) -> float:
        return max(self.y, self.y + self.height)

    @property
    def area(self) -> float:
        return abs(self.width * self.height)

    def contains(self, x: float, y: float, *, tolerance: float = 0.0) -> bool:
        return (
            self.x_min - tolerance <= x <= self.x_max + tolerance
            and self.y_min - tolerance <= y <= self.y_max + tolerance
        )


@dataclass(frozen=True)
class LegendBinding:
    product: str
    label_x: float
    label_y: float
    swatch: PaintedRectangle


@dataclass(frozen=True)
class ProductShareBinding:
    product: str
    percentage_token: str
    percentage_value: float
    token_x: float
    token_y: float
    segment: PaintedRectangle


@dataclass(frozen=True)
class OfficialIrQ2ProductAssignmentCertification:
    evidence_id: str
    share_column_evidence_id: str
    geometry_evidence_id: str
    source_certification_evidence_id: str
    observed_date: date
    source_url: str
    pdf_sha256: str
    page_number: int
    current_period_label: str
    legend_bindings: tuple[LegendBinding, ...]
    product_share_bindings: tuple[ProductShareBinding, ...]
    others_segment: PaintedRectangle
    dram_share_percent: float
    nand_share_percent: float
    other_share_percent: None
    product_assignment_certified: bool
    dram_nand_share_semantics_certified: bool
    others_segment_present: bool
    other_zero_certified: bool = False
    numeric_semantics_certified: bool = False
    registry_write_eligible: bool = False
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.evidence_id, "product-assignment evidence"),
            (self.share_column_evidence_id, "share-column evidence"),
            (self.geometry_evidence_id, "geometry evidence"),
            (self.source_certification_evidence_id, "source-certification evidence"),
            (self.pdf_sha256, "PDF"),
        ):
            if not _valid_sha(value):
                raise ValueError(f"SK hynix Q2 {label} ID must be SHA-256")
        if self.current_period_label != _CURRENT_PERIOD:
            raise ValueError("SK hynix Q2 product assignment must target '26 Q2")
        if not self.product_assignment_certified:
            raise ValueError("SK hynix Q2 product assignment must be certified")
        if not self.dram_nand_share_semantics_certified:
            raise ValueError("SK hynix Q2 DRAM/NAND share semantics must be certified")
        if not self.others_segment_present:
            raise ValueError("SK hynix Q2 Others display segment must remain explicit")
        if self.other_share_percent is not None:
            raise ValueError("SK hynix Q2 Other share must not be numerically inferred")
        if any(getattr(self, flag) for flag in _REQUIRED_FALSE_FLAGS):
            raise ValueError("SK hynix Q2 product assignment widened downstream trust")
        bindings = {item.product: item for item in self.product_share_bindings}
        if set(bindings) != {"DRAM", "NAND"}:
            raise ValueError("SK hynix Q2 product assignment requires DRAM and NAND bindings")
        if bindings["DRAM"].percentage_token != _EXPECTED_DRAM_TOKEN:
            raise ValueError("SK hynix Q2 DRAM token must remain 73%")
        if bindings["NAND"].percentage_token != _EXPECTED_NAND_TOKEN:
            raise ValueError("SK hynix Q2 NAND token must remain 27%")
        if self.dram_share_percent != 73.0 or self.nand_share_percent != 27.0:
            raise ValueError("SK hynix Q2 certified DRAM/NAND percentages drifted")


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _round(value: float) -> float:
    return round(float(value), 6)


def _fill_payload(item: FillStyle) -> dict[str, object]:
    return {
        "color_space": item.color_space,
        "components": [_round(value) for value in item.components],
    }


def _rectangle_payload(item: PaintedRectangle) -> dict[str, object]:
    return {
        "x": _round(item.x),
        "y": _round(item.y),
        "width": _round(item.width),
        "height": _round(item.height),
        "x_min": _round(item.x_min),
        "x_max": _round(item.x_max),
        "y_min": _round(item.y_min),
        "y_max": _round(item.y_max),
        "fill": _fill_payload(item.fill),
    }


def _legend_payload(item: LegendBinding) -> dict[str, object]:
    return {
        "product": item.product,
        "label_x": _round(item.label_x),
        "label_y": _round(item.label_y),
        "swatch": _rectangle_payload(item.swatch),
    }


def _binding_payload(item: ProductShareBinding) -> dict[str, object]:
    return {
        "product": item.product,
        "percentage_token": item.percentage_token,
        "percentage_value": item.percentage_value,
        "token_x": _round(item.token_x),
        "token_y": _round(item.token_y),
        "segment": _rectangle_payload(item.segment),
    }


def _certification_payload(
    item: OfficialIrQ2ProductAssignmentCertification,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_q2_product_assignment_certified",
        "evidence_id": item.evidence_id,
        "share_column_evidence_id": item.share_column_evidence_id,
        "geometry_evidence_id": item.geometry_evidence_id,
        "source_certification_evidence_id": item.source_certification_evidence_id,
        "observed_date": item.observed_date.isoformat(),
        "source_url": item.source_url,
        "pdf_sha256": item.pdf_sha256,
        "page_number": item.page_number,
        "current_period_label": item.current_period_label,
        "legend_bindings": [_legend_payload(value) for value in item.legend_bindings],
        "product_share_bindings": [
            _binding_payload(value) for value in item.product_share_bindings
        ],
        "others_segment": _rectangle_payload(item.others_segment),
        "dram_share_percent": item.dram_share_percent,
        "nand_share_percent": item.nand_share_percent,
        "other_share_percent": None,
        "product_assignment_certified": True,
        "dram_nand_share_semantics_certified": True,
        "others_segment_present": True,
        "other_zero_certified": False,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("’", "'").replace("‘", "'").split())


def _painted_rectangles(pdf_bytes: bytes, *, page_number: int) -> tuple[PaintedRectangle, ...]:
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("SK hynix Q2 assignment bytes do not start with a PDF signature")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise ValueError("SK hynix Q2 assignment PDF is unreadable") from exc
    if page_number <= 0 or page_number > len(reader.pages):
        raise ValueError("SK hynix Q2 assignment page number is out of range")
    page = reader.pages[page_number - 1]
    try:
        stream = ContentStream(page.get_contents(), reader)
    except Exception as exc:
        raise ValueError("SK hynix Q2 vector content stream is unreadable") from exc

    fill = FillStyle("gray", (0.0,))
    stack: list[FillStyle] = []
    pending: list[tuple[float, float, float, float]] = []
    painted: list[PaintedRectangle] = []

    def commit() -> None:
        for x, y, width, height in pending:
            if width == 0.0 or height == 0.0:
                continue
            painted.append(
                PaintedRectangle(
                    x=_round(x),
                    y=_round(y),
                    width=_round(width),
                    height=_round(height),
                    fill=fill,
                )
            )
        pending.clear()

    for operands, operator in stream.operations:
        if operator == b"q":
            stack.append(fill)
        elif operator == b"Q":
            pending.clear()
            fill = stack.pop() if stack else FillStyle("gray", (0.0,))
        elif operator == b"g":
            fill = FillStyle("gray", (_round(float(operands[0])),))
        elif operator == b"rg":
            fill = FillStyle(
                "rgb",
                tuple(_round(float(value)) for value in operands[:3]),
            )
        elif operator == b"re":
            if len(operands) != 4:
                raise ValueError("SK hynix Q2 rectangle operator shape is invalid")
            pending.append(tuple(float(value) for value in operands))
        elif operator in {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}:
            commit()
        elif operator in {b"n", b"S", b"s"}:
            pending.clear()
    return tuple(painted)


def _product_page(
    item: geometry.OfficialIrQ2ProductGeometry,
) -> geometry.ProductGeometryPage:
    if item.readiness_status != "geometry_ready_for_semantic_review":
        raise ValueError("SK hynix Q2 geometry is not ready for product assignment")
    if len(item.pages) != 1:
        raise ValueError("SK hynix Q2 product assignment requires exactly one product page")
    return item.pages[0]


def _label_fragment(
    page: geometry.ProductGeometryPage,
    product: str,
) -> geometry.TextFragment:
    midpoint = page.width / 2.0
    matches = [
        item
        for item in page.focus_fragments
        if item.text_x < midpoint and _normalize_text(item.text) == product
    ]
    if len(matches) != 1:
        raise ValueError(f"SK hynix Q2 {product} legend label is not unique")
    return matches[0]


def _legend_binding(
    page: geometry.ProductGeometryPage,
    rectangles: tuple[PaintedRectangle, ...],
    product: str,
) -> LegendBinding:
    label = _label_fragment(page, product)
    candidates: list[PaintedRectangle] = []
    for rectangle in rectangles:
        width = abs(rectangle.width)
        height = abs(rectangle.height)
        if not (0.0 < width <= _SMALL_SWATCH_MAX and 0.0 < height <= _SMALL_SWATCH_MAX):
            continue
        horizontal_gap = label.text_x - rectangle.x_max
        if horizontal_gap < -2.0 or horizontal_gap > _SWATCH_HORIZONTAL_GAP_MAX:
            continue
        if abs(((rectangle.y_min + rectangle.y_max) / 2.0) - label.text_y) > _SWATCH_VERTICAL_TOLERANCE:
            continue
        candidates.append(rectangle)
    if len(candidates) != 1:
        raise ValueError(f"SK hynix Q2 {product} legend swatch is not uniquely bound")
    return LegendBinding(
        product=product,
        label_x=label.text_x,
        label_y=label.text_y,
        swatch=candidates[0],
    )


def _current_token_fragments(
    item: geometry.OfficialIrQ2ProductGeometry,
) -> tuple[geometry.TextFragment, geometry.TextFragment]:
    page = _product_page(item)
    clusters = share._cluster_percentages(page)
    current = clusters[-1]
    tokens = tuple(fragment.text.strip() for fragment in current)
    if tokens != (_EXPECTED_DRAM_TOKEN, _EXPECTED_NAND_TOKEN):
        raise ValueError("SK hynix Q2 current share tokens drifted before product assignment")
    return current[0], current[1]


def _segment_for_token(
    rectangles: tuple[PaintedRectangle, ...],
    *,
    token: geometry.TextFragment,
    fill: FillStyle,
    product: str,
) -> PaintedRectangle:
    candidates = [
        item
        for item in rectangles
        if item.fill == fill
        and abs(item.width) >= _SEGMENT_MIN_WIDTH
        and item.contains(
            token.text_x,
            token.text_y,
            tolerance=_SEGMENT_TOKEN_TOLERANCE,
        )
    ]
    if len(candidates) != 1:
        raise ValueError(f"SK hynix Q2 {product} token is not uniquely inside its legend colour")
    return candidates[0]


def _others_segment(
    rectangles: tuple[PaintedRectangle, ...],
    *,
    fill: FillStyle,
    x_center: float,
    reference_width: float,
) -> PaintedRectangle:
    candidates = [
        item
        for item in rectangles
        if item.fill == fill
        and item.area > 0.0
        and item.contains(x_center, (item.y_min + item.y_max) / 2.0)
        and abs(abs(item.width) - reference_width) <= _SEGMENT_X_TOLERANCE
    ]
    if len(candidates) != 1:
        raise ValueError("SK hynix Q2 current Others display segment is not uniquely verified")
    return candidates[0]


def _verify_current_stack(
    dram: PaintedRectangle,
    nand: PaintedRectangle,
    others: PaintedRectangle,
) -> None:
    rectangles = (dram, nand, others)
    x_mins = [item.x_min for item in rectangles]
    x_maxs = [item.x_max for item in rectangles]
    if max(x_mins) - min(x_mins) > _SEGMENT_X_TOLERANCE:
        raise ValueError("SK hynix Q2 current product segments do not share an x origin")
    if max(x_maxs) - min(x_maxs) > _SEGMENT_X_TOLERANCE:
        raise ValueError("SK hynix Q2 current product segments do not share a width")

    ordered = sorted(rectangles, key=lambda item: item.y_min)
    for lower, upper in zip(ordered, ordered[1:], strict=True):
        if abs(lower.y_max - upper.y_min) > _SEGMENT_CONTIGUITY_TOLERANCE:
            raise ValueError("SK hynix Q2 current product segments are not contiguous")
    if ordered != [dram, nand, others]:
        raise ValueError("SK hynix Q2 current product stack order drifted")


def build_q2_product_assignment_certification(
    share_item: share.OfficialIrQ2ShareColumnCertification,
    geometry_item: geometry.OfficialIrQ2ProductGeometry,
    *,
    pdf_bytes: bytes,
) -> OfficialIrQ2ProductAssignmentCertification:
    if not share_item.period_column_semantics_certified:
        raise ValueError("SK hynix Q2 share-column semantics are not certified")
    if share_item.current_period_label != _CURRENT_PERIOD:
        raise ValueError("SK hynix Q2 share-column period drifted")
    if share_item.current_column_percentage_tokens != (
        _EXPECTED_DRAM_TOKEN,
        _EXPECTED_NAND_TOKEN,
    ):
        raise ValueError("SK hynix Q2 share-column token pair drifted")
    if share_item.geometry_evidence_id != geometry_item.evidence_id:
        raise ValueError("SK hynix Q2 assignment geometry evidence does not match share column")
    if share_item.source_certification_evidence_id != geometry_item.source_certification_evidence_id:
        raise ValueError("SK hynix Q2 assignment source-certification chain diverged")
    if share_item.pdf_sha256 != geometry_item.pdf_sha256:
        raise ValueError("SK hynix Q2 assignment PDF hash chain diverged")
    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    if pdf_sha != share_item.pdf_sha256:
        raise ValueError("SK hynix Q2 assignment PDF bytes differ from certified source")

    page = _product_page(geometry_item)
    if page.page_number != share_item.page_number:
        raise ValueError("SK hynix Q2 assignment page differs from share-column page")
    rectangles = _painted_rectangles(pdf_bytes, page_number=page.page_number)
    legend = tuple(_legend_binding(page, rectangles, product) for product in _PRODUCTS)
    legend_by_product = {item.product: item for item in legend}
    if len({item.swatch.fill for item in legend}) != len(_PRODUCTS):
        raise ValueError("SK hynix Q2 product legend fill styles are not distinct")

    dram_token, nand_token = _current_token_fragments(geometry_item)
    dram_segment = _segment_for_token(
        rectangles,
        token=dram_token,
        fill=legend_by_product["DRAM"].swatch.fill,
        product="DRAM",
    )
    nand_segment = _segment_for_token(
        rectangles,
        token=nand_token,
        fill=legend_by_product["NAND"].swatch.fill,
        product="NAND",
    )
    x_center = share_item.columns[-1].x_center
    others_segment = _others_segment(
        rectangles,
        fill=legend_by_product["Others"].swatch.fill,
        x_center=x_center,
        reference_width=abs(dram_segment.width),
    )
    _verify_current_stack(dram_segment, nand_segment, others_segment)
    if others_segment.contains(dram_token.text_x, dram_token.text_y) or others_segment.contains(
        nand_token.text_x, nand_token.text_y
    ):
        raise ValueError("SK hynix Q2 unlabeled Others segment contains a share token")

    bindings = (
        ProductShareBinding(
            product="DRAM",
            percentage_token=dram_token.text.strip(),
            percentage_value=73.0,
            token_x=dram_token.text_x,
            token_y=dram_token.text_y,
            segment=dram_segment,
        ),
        ProductShareBinding(
            product="NAND",
            percentage_token=nand_token.text.strip(),
            percentage_value=27.0,
            token_x=nand_token.text_x,
            token_y=nand_token.text_y,
            segment=nand_segment,
        ),
    )
    provisional = {
        "share_column_evidence_id": share_item.evidence_id,
        "geometry_evidence_id": geometry_item.evidence_id,
        "source_certification_evidence_id": geometry_item.source_certification_evidence_id,
        "observed_date": geometry_item.observed_date.isoformat(),
        "source_url": geometry_item.source_url,
        "pdf_sha256": geometry_item.pdf_sha256,
        "page_number": page.page_number,
        "current_period_label": _CURRENT_PERIOD,
        "legend_bindings": [_legend_payload(value) for value in legend],
        "product_share_bindings": [_binding_payload(value) for value in bindings],
        "others_segment": _rectangle_payload(others_segment),
        "dram_share_percent": 73.0,
        "nand_share_percent": 27.0,
        "other_share_percent": None,
        "product_assignment_certified": True,
        "dram_nand_share_semantics_certified": True,
        "others_segment_present": True,
        "other_zero_certified": False,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrQ2ProductAssignmentCertification(
        evidence_id=_sha_payload(provisional),
        share_column_evidence_id=share_item.evidence_id,
        geometry_evidence_id=geometry_item.evidence_id,
        source_certification_evidence_id=geometry_item.source_certification_evidence_id,
        observed_date=geometry_item.observed_date,
        source_url=geometry_item.source_url,
        pdf_sha256=geometry_item.pdf_sha256,
        page_number=page.page_number,
        current_period_label=_CURRENT_PERIOD,
        legend_bindings=legend,
        product_share_bindings=bindings,
        others_segment=others_segment,
        dram_share_percent=73.0,
        nand_share_percent=27.0,
        other_share_percent=None,
        product_assignment_certified=True,
        dram_nand_share_semantics_certified=True,
        others_segment_present=True,
    )


def _load_inputs_from_share_pointer(
    share_pointer_path: Path,
    *,
    evaluation_date: date,
) -> tuple[
    share.OfficialIrQ2ShareColumnCertification,
    geometry.OfficialIrQ2ProductGeometry,
    bytes,
    Path,
]:
    share_item = load_q2_share_column_certification(
        share_pointer_path,
        evaluation_date=evaluation_date,
    )
    try:
        pointer_obj: object = json.loads(share_pointer_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 share-column pointer is unreadable for assignment") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 share-column pointer must be an object for assignment")
    geometry_pointer = Path(str(pointer_obj.get("geometry_pointer_path", "")))
    geometry_item = load_q2_product_geometry(
        geometry_pointer,
        evaluation_date=evaluation_date,
    )
    try:
        geometry_pointer_obj: object = json.loads(
            geometry_pointer.read_text(encoding="utf-8")
        )
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 geometry pointer is unreadable for assignment") from exc
    if not isinstance(geometry_pointer_obj, dict):
        raise ValueError("SK hynix Q2 geometry pointer must be an object for assignment")
    source_pointer = Path(
        str(geometry_pointer_obj.get("source_certification_pointer_path", ""))
    )
    pdf_bytes = geometry._load_pdf_bytes_from_certification_pointer(source_pointer)
    return share_item, geometry_item, pdf_bytes, geometry_pointer


def capture_q2_product_assignment_certification(
    share_pointer_path: str | Path = share.DEFAULT_Q2_SHARE_COLUMN_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_Q2_PRODUCT_ASSIGNMENT_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    pointer_path = Path(share_pointer_path)
    share_item, geometry_item, pdf_bytes, geometry_pointer = _load_inputs_from_share_pointer(
        pointer_path,
        evaluation_date=evaluation_date,
    )
    certification = build_q2_product_assignment_certification(
        share_item,
        geometry_item,
        pdf_bytes=pdf_bytes,
    )

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
        raise ValueError("SK hynix Q2 product-assignment artifact path already exists")
    temporary.mkdir()
    try:
        report_path = temporary / "product_assignment_certification.json"
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
        "share_column_pointer_path": str(pointer_path.resolve()),
        "geometry_pointer_path": str(geometry_pointer.resolve()),
        "artifact_directory": str(directory.resolve()),
        "report_path": str(
            (directory / "product_assignment_certification.json").resolve()
        ),
    }
    temporary_pointer = root / ".latest_skhynix_ir_q2_product_assignment_certification.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(root / DEFAULT_Q2_PRODUCT_ASSIGNMENT_POINTER.name)
    return pointer_payload


__all__ = [
    "DEFAULT_Q2_PRODUCT_ASSIGNMENT_OUTPUT",
    "DEFAULT_Q2_PRODUCT_ASSIGNMENT_POINTER",
    "FillStyle",
    "LegendBinding",
    "OfficialIrQ2ProductAssignmentCertification",
    "PaintedRectangle",
    "ProductShareBinding",
    "build_q2_product_assignment_certification",
    "capture_q2_product_assignment_certification",
]
