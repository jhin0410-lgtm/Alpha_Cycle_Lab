"""Extract issuer-reported pre-2023 SK hynix ASP and shipment language from DART filings.

This layer preserves what the filing actually says.  It may normalize qualitative language
into the same vocabulary used by interval sensitivity, but that normalization is explicitly
a method assumption rather than a numeric source fact.  Nothing here creates a point
estimate, certifies a four-field estimation row, or enables fitting.
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
_MAGNITUDE_RE = re.compile(
    r"(?P<phrase>"
    r"한\s*자릿수\s*(?:초반|중반|후반)|"
    r"(?:10|20|30)%\s*(?:초반|중반|후반)|"
    r"약\s*\d+(?:\.\d+)?%\s*(?:수준)?|"
    r"\d+(?:\.\d+)?%\s*이상|"
    r"\d+(?:\.\d+)?%\s*내외|"
    r"\d+(?:\.\d+)?%"
    r")"
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
    )


def _nearest_product(text: str, position: int) -> str | None:
    candidates: list[tuple[int, str]] = []
    for marker, product in (("DRAM", "dram"), ("NAND", "nand"), ("낸드", "nand")):
        for match in re.finditer(marker, text, flags=re.IGNORECASE):
            if match.start() <= position:
                candidates.append((match.start(), product))
    return max(candidates)[1] if candidates else None


def _nearest_metric(text: str, start: int, end: int) -> str | None:
    candidates: list[tuple[int, str]] = []
    for marker, metric in (("ASP", "asp"), ("출하량", "bit_volume")):
        for match in re.finditer(marker, text, flags=re.IGNORECASE):
            distance = min(abs(match.start() - start), abs(match.start() - end))
            if distance <= 130:
                candidates.append((distance, metric))
    return min(candidates)[1] if candidates else None


def _direction(window: str) -> str | None:
    folded = window.casefold()
    increase = min(
        (folded.find(token) for token in ("증가", "상승") if token in folded),
        default=-1,
    )
    decrease = min(
        (folded.find(token) for token in ("감소", "하락") if token in folded),
        default=-1,
    )
    if increase < 0 and decrease < 0:
        return None
    if increase < 0:
        return "decrease"
    if decrease < 0:
        return "increase"
    return "increase" if increase < decrease else "decrease"


def _basis(window: str, product: str) -> str:
    folded = window.casefold()
    solidigm = "solidigm" in folded or "솔리다임" in folded
    hq = "본사 기준" in window
    if solidigm and hq:
        return "solidigm_integrated_and_hq"
    if solidigm:
        return "solidigm_integrated"
    if hq:
        return "hq"
    return "issuer_unspecified" if product == "nand" else "issuer_reported"


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


def _claims_for_line(
    period_id: str,
    line: str,
    *,
    text_sha256: str,
) -> tuple[Pre2023CycleDriverClaim, ...]:
    results: list[Pre2023CycleDriverClaim] = []
    for match in _MAGNITUDE_RE.finditer(line):
        product = _nearest_product(line, match.start())
        metric = _nearest_metric(line, match.start(), match.end())
        if product is None or metric is None:
            continue
        window_start = max(0, match.start() - 100)
        window_end = min(len(line), match.end() + 120)
        window = line[window_start:window_end]
        direction = _direction(line[match.start() : min(len(line), match.end() + 80)])
        if direction is None:
            direction = _direction(window)
        if direction is None:
            continue
        source_magnitude = _normalize_space(match.group("phrase"))
        normalized = _normalized_interval_text(source_magnitude, direction)
        stable = {
            "period_id": period_id,
            "product": product,
            "metric": metric,
            "basis": _basis(window, product),
            "direction": direction,
            "source_magnitude_text": source_magnitude,
            "normalized_interval_text": normalized,
            "source_excerpt": line,
            "normalized_text_sha256": text_sha256,
            "numeric_point_source_fact": False,
            "estimation_input_ready": False,
        }
        results.append(
            Pre2023CycleDriverClaim(
                evidence_id=_sha(stable),
                period_id=period_id,
                product=product,
                metric=metric,
                basis=str(stable["basis"]),
                direction=direction,
                source_magnitude_text=source_magnitude,
                normalized_interval_text=normalized,
                source_excerpt=line,
                normalized_text_sha256=text_sha256,
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
