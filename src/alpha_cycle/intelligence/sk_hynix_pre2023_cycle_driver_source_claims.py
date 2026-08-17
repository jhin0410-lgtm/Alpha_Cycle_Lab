"""Extract current-period SK hynix ASP and shipment claims from preserved DART text.

The source layer is intentionally narrow. It accepts only current-quarter operational
language that ties product, metric, direction, and (when present) magnitude together.
Historical market-size narrative, company revenue growth, and operating-profit changes are
not product-driver claims. Qualitative magnitudes remain interval-method assumptions only.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
    load_failure_diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
)

_EXPECTED_PERIODS = (
    "2021Q1",
    "2021Q2",
    "2021Q3",
    "2022Q1",
    "2022Q2",
    "2022Q3",
)
_MAGNITUDE_PATTERN = (
    r"(?:"
    r"한\s*자릿수\s*(?:초반|중반|후반)|"
    r"(?:10|20|30)%\s*(?:초반|중반|후반)|"
    r"약\s*\d+(?:\.\d+)?%\s*(?:수준)?|"
    r"\d+(?:\.\d+)?%\s*이상|"
    r"\d+(?:\.\d+)?%\s*내외|"
    r"\d+(?:\.\d+)?%"
    r")"
)
_METRIC_FIRST_RE = re.compile(
    rf"(?P<metric>ASP|출하량)(?:은|는|이|가)?"
    rf"(?P<middle>[^.,;。]{{0,90}}?)"
    rf"(?P<phrase>{_MAGNITUDE_PATTERN})"
    rf"\s*(?:수준)?\s*(?:으로)?\s*"
    rf"(?P<direction>증가|상승|감소|하락)",
    flags=re.IGNORECASE,
)
_MAGNITUDE_FIRST_RE = re.compile(
    rf"(?P<phrase>{_MAGNITUDE_PATTERN})"
    rf"\s*(?:수준)?\s*(?:으로)?\s*(?:의\s*)?"
    rf"(?P<metric>ASP|출하량)(?:은|는|이|가)?\s*"
    rf"(?P<direction>증가|상승|감소|하락)",
    flags=re.IGNORECASE,
)
_PRODUCT_RE = re.compile(r"DRAM|NAND|낸드", flags=re.IGNORECASE)
_CURRENT_COMPARISON_RE = re.compile(r"(?:전\s*분기|전분기|직전\s*분기)\s*대비")
_DIRECTION_RE = re.compile(
    r"(?P<metric>ASP|출하량)(?:은|는|이|가)?\s*(?P<direction>증가|상승|감소|하락)"
)
_BOTH_PRODUCTS_RE = re.compile(
    r"DRAM\s*(?:과|및|/)\s*(?:NAND|낸드)\s*모두",
    flags=re.IGNORECASE,
)


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _latest_diagnostic_path(period_root: Path) -> Path:
    failed = period_root / "failed"
    if not failed.is_dir():
        raise ValueError(f"Pre-2023 cycle-driver failure root is missing: {period_root}")
    candidates = sorted(
        (item / "diagnostic.json" for item in failed.iterdir() if item.is_dir()),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise ValueError(f"Pre-2023 cycle-driver diagnostic is missing: {period_root}")
    return path


def _normalize_space(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


def _source_lines(diagnostic: HistoricalProductRevenueFailureDiagnostic) -> tuple[str, ...]:
    text = Path(diagnostic.normalized_text_path).read_text(encoding="utf-8")
    return tuple(
        line
        for raw in text.splitlines()
        if (line := _normalize_space(raw))
        and ("ASP" in line or "출하량" in line)
        and ("DRAM" in line or "NAND" in line or "낸드" in line)
        and _CURRENT_COMPARISON_RE.search(line) is not None
    )


def _product_before(text: str, position: int) -> tuple[str, int] | None:
    candidates: list[tuple[int, str]] = []
    for match in _PRODUCT_RE.finditer(text):
        if match.start() > position:
            break
        token = match.group(0).casefold()
        product = "dram" if token == "dram" else "nand"
        candidates.append((match.start(), product))
    if not candidates:
        return None
    start, product = max(candidates)
    return product, start


def _sentence_excerpt(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("。", 0, start))
    left = 0 if left < 0 else left + 1
    dot = text.find(".", end)
    ideographic = text.find("。", end)
    right_candidates = [value for value in (dot, ideographic) if value >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return _normalize_space(text[left:right])


def _basis(excerpt: str, product: str) -> str:
    folded = excerpt.casefold()
    solidigm = "solidigm" in folded or "솔리다임" in excerpt
    hq = "본사 기준" in excerpt
    if solidigm and hq:
        return "solidigm_integrated_and_hq"
    if solidigm:
        return "solidigm_integrated"
    if hq:
        return "hq"
    return "issuer_reported" if product == "dram" else "issuer_unspecified"


def _normalized_interval_text(phrase: str, direction: str) -> str | None:
    compact = re.sub(r"\s+", " ", phrase).strip()
    suffix = "Increase" if direction == "increase" else "Decrease"
    aliases = {
        "한 자릿수 초반": "Low-single%",
        "한 자릿수 중반": "Mid-single%",
        "한 자릿수 후반": "High-single%",
        "10% 초반": "Low-teen%",
        "10% 중반": "Mid-teen%",
        "10% 후반": "High-teen%",
        "20% 초반": "Low-20%",
        "20% 중반": "Mid-20%",
        "30% 중반": "Mid-30%",
    }
    if compact in aliases:
        return f"{aliases[compact]} {suffix}"
    around = re.fullmatch(r"약\s*(\d+(?:\.\d+)?)%\s*(?:수준)?", compact)
    if around is not None:
        return f"Around {around.group(1)}% {suffix}"
    over = re.fullmatch(r"(\d+(?:\.\d+)?)%\s*이상", compact)
    if over is not None:
        return f"Over {over.group(1)}% {suffix}"
    near = re.fullmatch(r"(\d+(?:\.\d+)?)%\s*내외", compact)
    if near is not None:
        return f"Around {near.group(1)}% {suffix}"
    exact = re.fullmatch(r"(\d+(?:\.\d+)?)%", compact)
    if exact is not None:
        return f"Around {exact.group(1)}% {suffix}"
    return None


def _direction(value: str) -> str:
    return "increase" if value in {"증가", "상승"} else "decrease"


@dataclass(frozen=True)
class Pre2023CycleDriverClaim:
    evidence_id: str
    period_id: str
    product: str
    metric: str
    basis: str
    direction: str
    source_magnitude_text: str
    normalized_interval_text: str | None
    source_excerpt: str
    normalized_text_sha256: str
    issuer_driver_language_source_fact: bool = True
    normalized_interval_is_method_assumption: bool = True
    numeric_point_source_fact: bool = False
    estimation_input_ready: bool = False
    four_field_driver_certified: bool = False
    fit_enabled: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Pre-2023 cycle-driver period is unsupported")
        if self.product not in {"dram", "nand"} or self.metric not in {"asp", "bit_volume"}:
            raise ValueError("Pre-2023 cycle-driver product/metric is invalid")
        if self.direction not in {"increase", "decrease"}:
            raise ValueError("Pre-2023 cycle-driver direction is invalid")
        if len(self.evidence_id) != 64 or len(self.normalized_text_sha256) != 64:
            raise ValueError("Pre-2023 cycle-driver hashes must be SHA-256")
        if not self.source_magnitude_text or not self.source_excerpt:
            raise ValueError("Pre-2023 cycle-driver source evidence is incomplete")
        if (
            not self.issuer_driver_language_source_fact
            or not self.normalized_interval_is_method_assumption
            or self.numeric_point_source_fact
            or self.estimation_input_ready
            or self.four_field_driver_certified
            or self.fit_enabled
        ):
            raise ValueError("Pre-2023 cycle-driver claim exceeded trust boundary")


@dataclass(frozen=True)
class Pre2023CycleDriverPeriodProfile:
    evidence_id: str
    period_id: str
    rcept_no: str
    source_excerpt_count: int
    claims: tuple[Pre2023CycleDriverClaim, ...]
    claim_count: int
    dram_asp_claim_count: int
    dram_bit_volume_claim_count: int
    nand_asp_claim_count: int
    nand_bit_volume_claim_count: int
    source_language_four_field_coverage: bool
    four_field_driver_certified: bool = False
    estimation_input_ready: bool = False
    fit_enabled: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS or len(self.evidence_id) != 64:
            raise ValueError("Pre-2023 cycle-driver period profile identity is invalid")
        if self.claim_count != len(self.claims):
            raise ValueError("Pre-2023 cycle-driver claim count is inconsistent")
        counts = {
            ("dram", "asp"): self.dram_asp_claim_count,
            ("dram", "bit_volume"): self.dram_bit_volume_claim_count,
            ("nand", "asp"): self.nand_asp_claim_count,
            ("nand", "bit_volume"): self.nand_bit_volume_claim_count,
        }
        for key, expected in counts.items():
            actual = sum((item.product, item.metric) == key for item in self.claims)
            if actual != expected:
                raise ValueError("Pre-2023 cycle-driver metric count is inconsistent")
        complete = all(value > 0 for value in counts.values())
        if self.source_language_four_field_coverage != complete:
            raise ValueError("Pre-2023 four-field source-language coverage is inconsistent")
        if self.four_field_driver_certified or self.estimation_input_ready or self.fit_enabled:
            raise ValueError("Pre-2023 cycle-driver profile exceeded trust boundary")


def _claim(
    *,
    period_id: str,
    product: str,
    metric: str,
    basis: str,
    direction: str,
    source_magnitude: str,
    normalized: str | None,
    excerpt: str,
    text_sha256: str,
) -> Pre2023CycleDriverClaim:
    stable = {
        "period_id": period_id,
        "product": product,
        "metric": metric,
        "basis": basis,
        "direction": direction,
        "source_magnitude_text": source_magnitude,
        "normalized_interval_text": normalized,
        "source_excerpt": excerpt,
        "normalized_text_sha256": text_sha256,
        "numeric_point_source_fact": False,
        "estimation_input_ready": False,
    }
    return Pre2023CycleDriverClaim(
        evidence_id=_sha(stable),
        period_id=period_id,
        product=product,
        metric=metric,
        basis=basis,
        direction=direction,
        source_magnitude_text=source_magnitude,
        normalized_interval_text=normalized,
        source_excerpt=excerpt,
        normalized_text_sha256=text_sha256,
    )


def _magnitude_claims_for_line(
    period_id: str,
    line: str,
    *,
    text_sha256: str,
) -> tuple[Pre2023CycleDriverClaim, ...]:
    results: list[Pre2023CycleDriverClaim] = []
    for pattern in (_METRIC_FIRST_RE, _MAGNITUDE_FIRST_RE):
        for match in pattern.finditer(line):
            middle = match.groupdict().get("middle")
            if middle is not None and ("매출" in middle or "영업이익" in middle):
                continue
            metric_token = match.group("metric").casefold()
            metric = "asp" if metric_token == "asp" else "bit_volume"
            product_match = _product_before(line, match.start("metric"))
            if product_match is None:
                continue
            product, _product_start = product_match
            direction = _direction(match.group("direction"))
            source_magnitude = _normalize_space(match.group("phrase"))
            excerpt = _sentence_excerpt(line, match.start(), match.end())
            results.append(
                _claim(
                    period_id=period_id,
                    product=product,
                    metric=metric,
                    basis=_basis(excerpt, product),
                    direction=direction,
                    source_magnitude=source_magnitude,
                    normalized=_normalized_interval_text(source_magnitude, direction),
                    excerpt=excerpt,
                    text_sha256=text_sha256,
                )
            )
    unique: dict[tuple[str, str, str, str, str], Pre2023CycleDriverClaim] = {}
    for item in results:
        key = (
            item.product,
            item.metric,
            item.basis,
            item.source_magnitude_text,
            item.direction,
        )
        unique[key] = item
    return tuple(unique.values())


def _direction_only_group_claims(
    period_id: str,
    line: str,
    *,
    text_sha256: str,
    existing: tuple[Pre2023CycleDriverClaim, ...],
) -> tuple[Pre2023CycleDriverClaim, ...]:
    covered = {(item.product, item.metric) for item in existing}
    results: list[Pre2023CycleDriverClaim] = []
    for group in _BOTH_PRODUCTS_RE.finditer(line):
        excerpt = _sentence_excerpt(line, group.start(), group.end())
        if _CURRENT_COMPARISON_RE.search(excerpt) is None:
            continue
        metric_directions = {
            (
                "asp" if match.group("metric").casefold() == "asp" else "bit_volume",
                _direction(match.group("direction")),
            )
            for match in _DIRECTION_RE.finditer(excerpt)
        }
        for product in ("dram", "nand"):
            for metric, direction in metric_directions:
                if (product, metric) in covered:
                    continue
                results.append(
                    _claim(
                        period_id=period_id,
                        product=product,
                        metric=metric,
                        basis="issuer_reported_direction_only",
                        direction=direction,
                        source_magnitude="direction_only",
                        normalized=None,
                        excerpt=excerpt,
                        text_sha256=text_sha256,
                    )
                )
                covered.add((product, metric))
    return tuple(results)


def _claims_for_line(
    period_id: str,
    line: str,
    *,
    text_sha256: str,
) -> tuple[Pre2023CycleDriverClaim, ...]:
    magnitude = _magnitude_claims_for_line(period_id, line, text_sha256=text_sha256)
    direction_only = _direction_only_group_claims(
        period_id,
        line,
        text_sha256=text_sha256,
        existing=magnitude,
    )
    return (*magnitude, *direction_only)


def build_pre2023_cycle_driver_profile(
    diagnostic: HistoricalProductRevenueFailureDiagnostic,
) -> Pre2023CycleDriverPeriodProfile:
    lines = _source_lines(diagnostic)
    claims = tuple(
        claim
        for line in lines
        for claim in _claims_for_line(
            diagnostic.period_id,
            line,
            text_sha256=diagnostic.text_sha256,
        )
    )
    unique: dict[tuple[str, str, str, str, str], Pre2023CycleDriverClaim] = {}
    for item in claims:
        key = (
            item.product,
            item.metric,
            item.basis,
            item.source_magnitude_text,
            item.direction,
        )
        unique[key] = item
    claims = tuple(unique.values())
    counts = {
        (product, metric): sum(
            item.product == product and item.metric == metric for item in claims
        )
        for product in ("dram", "nand")
        for metric in ("asp", "bit_volume")
    }
    stable = {
        "period_id": diagnostic.period_id,
        "rcept_no": diagnostic.rcept_no,
        "normalized_text_sha256": diagnostic.text_sha256,
        "source_excerpts": lines,
        "claims": [asdict(item) for item in claims],
        "four_field_driver_certified": False,
        "estimation_input_ready": False,
    }
    return Pre2023CycleDriverPeriodProfile(
        evidence_id=_sha(stable),
        period_id=diagnostic.period_id,
        rcept_no=diagnostic.rcept_no,
        source_excerpt_count=len(lines),
        claims=claims,
        claim_count=len(claims),
        dram_asp_claim_count=counts[("dram", "asp")],
        dram_bit_volume_claim_count=counts[("dram", "bit_volume")],
        nand_asp_claim_count=counts[("nand", "asp")],
        nand_bit_volume_claim_count=counts[("nand", "bit_volume")],
        source_language_four_field_coverage=all(value > 0 for value in counts.values()),
    )


def profile_pre2023_cycle_driver_sources(
    *,
    output: str | Path = DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
) -> tuple[Pre2023CycleDriverPeriodProfile, ...]:
    root = Path(output)
    results: list[Pre2023CycleDriverPeriodProfile] = []
    for period_id in _EXPECTED_PERIODS:
        diagnostic = load_failure_diagnostic(
            period_id,
            _latest_diagnostic_path(root / period_id),
        )
        results.append(build_pre2023_cycle_driver_profile(diagnostic))
    return tuple(results)


__all__ = [
    "Pre2023CycleDriverClaim",
    "Pre2023CycleDriverPeriodProfile",
    "build_pre2023_cycle_driver_profile",
    "profile_pre2023_cycle_driver_sources",
]
