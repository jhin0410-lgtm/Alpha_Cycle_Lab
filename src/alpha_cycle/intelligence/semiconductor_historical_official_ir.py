"""Historical official-IR evidence that is explicitly excluded from current live coverage.

This module preserves what an issuer's currently accessible official historical page says,
but it does not claim that the bytes available today are a point-in-time archive of what
was observable on the publisher's stated publication date. Historical page metadata,
current captured bytes, and current live forward coverage are therefore separate concepts.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import yaml

DEFAULT_HISTORICAL_IR_REGISTRY = Path("config/semiconductor_historical_ir_documents.yaml")


@dataclass(frozen=True)
class HistoricalOfficialIrSpec:
    document_id: str
    ticker: str
    issuer_name: str
    source_id: str
    document_role: str
    content_type: str
    source_url: str
    source_published_date: date
    period_start: date
    period_end: date
    parser_id: str
    current_refresh_eligible: bool
    required_identity_anchors: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Historical official IR ticker must be six digits")
        if self.content_type != "html":
            raise ValueError("Historical official IR v1 supports registered HTML only")
        if self.current_refresh_eligible:
            raise ValueError("Historical official IR documents cannot be current-refresh eligible")
        host = (urlparse(self.source_url).hostname or "").casefold()
        if self.source_id == "sk_hynix_ir" and not (
            host == "news.skhynix.com" or host.endswith(".news.skhynix.com")
        ):
            raise ValueError("SK hynix historical IR must stay on the official Newsroom domain")
        if self.period_start > self.period_end:
            raise ValueError("Historical official IR accounting period is invalid")
        if self.source_published_date < self.period_end:
            raise ValueError("Historical official IR publication cannot precede period end")
        if not self.required_identity_anchors:
            raise ValueError("Historical official IR requires identity anchors")


@dataclass(frozen=True)
class HistoricalCompanyFact:
    metric_id: str
    value: float
    unit: str


@dataclass(frozen=True)
class HistoricalForwardClaim:
    ticker: str
    block_id: str
    metric_id: str
    statement: str
    period_start: date
    period_end: date

    def __post_init__(self) -> None:
        if self.period_start > self.period_end:
            raise ValueError("Historical forward claim period is invalid")


@dataclass(frozen=True)
class ParsedHistoricalOfficialIr:
    spec: HistoricalOfficialIrSpec
    source_document_sha256: str
    visible_text: str
    company_facts: tuple[HistoricalCompanyFact, ...]
    forward_claims: tuple[HistoricalForwardClaim, ...]
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    current_forward_coverage_eligible: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.source_document_sha256) != 64:
            raise ValueError("Historical official IR source hash must be SHA-256")
        if not self.visible_text or not self.company_facts or not self.forward_claims:
            raise ValueError("Historical official IR requires parsed facts and forward claims")
        if (
            self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.current_forward_coverage_eligible
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Historical official IR v1 must remain retrospective and non-scoring")


class _VisibleTextParser(HTMLParser):
    _IGNORED = frozenset({"script", "style", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() in self._IGNORED:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self._IGNORED and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0 and data.strip():
            self.parts.append(data)


def _strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Historical official IR {label} must be boolean")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Historical official IR {label} must be an array")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if not result:
        raise ValueError(f"Historical official IR {label} cannot be empty")
    return result


def load_historical_official_ir_registry(
    path: str | Path = DEFAULT_HISTORICAL_IR_REGISTRY,
) -> dict[str, HistoricalOfficialIrSpec]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), dict):
        raise ValueError("Historical official IR registry must contain documents")
    result: dict[str, HistoricalOfficialIrSpec] = {}
    for raw_id, raw_value in cast(dict[object, object], payload["documents"]).items():
        document_id = str(raw_id).strip()
        if not isinstance(raw_value, dict):
            raise ValueError(f"Historical official IR document must be an object: {document_id}")
        raw = cast(dict[object, object], raw_value)
        spec = HistoricalOfficialIrSpec(
            document_id=document_id,
            ticker=str(raw.get("ticker", "")).strip().zfill(6),
            issuer_name=str(raw.get("issuer_name", "")).strip(),
            source_id=str(raw.get("source_id", "")).strip(),
            document_role=str(raw.get("document_role", "")).strip(),
            content_type=str(raw.get("content_type", "")).strip(),
            source_url=str(raw.get("source_url", "")).strip(),
            source_published_date=date.fromisoformat(str(raw.get("source_published_date", ""))),
            period_start=date.fromisoformat(str(raw.get("period_start", ""))),
            period_end=date.fromisoformat(str(raw.get("period_end", ""))),
            parser_id=str(raw.get("parser_id", "")).strip(),
            current_refresh_eligible=_strict_bool(
                raw.get("current_refresh_eligible"), "current_refresh_eligible"
            ),
            required_identity_anchors=_string_tuple(
                raw.get("required_identity_anchors", []), "required_identity_anchors"
            ),
        )
        if document_id in result:
            raise ValueError(f"Historical official IR document is duplicated: {document_id}")
        result[document_id] = spec
    if not result:
        raise ValueError("Historical official IR registry is empty")
    return result


def extract_visible_html_text(data: bytes) -> str:
    parser = _VisibleTextParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    parser.close()
    text = " ".join(" ".join(parser.parts).replace("\u00a0", " ").split())
    if not text:
        raise ValueError("Historical official IR HTML has no visible text")
    return text


def _require(text: str, anchor: str, label: str) -> None:
    if anchor.casefold() not in text.casefold():
        raise ValueError(f"Historical official IR anchor missing: {label}")


def _number(text: str, pattern: str, label: str) -> float:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        raise ValueError(f"Historical official IR number missing: {label}")
    return float(match.group(1).replace(",", ""))


def parse_skhynix_2026q1_newsroom(
    spec: HistoricalOfficialIrSpec,
    data: bytes,
) -> ParsedHistoricalOfficialIr:
    if spec.parser_id != "skhynix_newsroom_2026q1_v1":
        raise ValueError("SK hynix historical parser received the wrong parser_id")
    text = extract_visible_html_text(data)
    for anchor in spec.required_identity_anchors:
        _require(text, anchor, anchor)
    _require(
        text,
        "favorable pricing conditions will continue for both DRAM and NAND flash",
        "DRAM/NAND pricing outlook",
    )
    _require(
        text,
        "high-value-added products, including HBM, high-capacity server DRAM modules, and eSSDs",
        "high-value product mix",
    )
    _require(text, "performance, yield, quality, and supply stability", "HBM capability")
    _require(text, "customer demand exceeds supply capacity", "supply capacity")
    _require(text, "leveraging synergies with Solidigm", "Solidigm/eSSD")

    facts = (
        HistoricalCompanyFact(
            "revenue",
            _number(text, r"recorded\s+([0-9.]+)\s+trillion won in revenue", "revenue"),
            "KRW_trillion",
        ),
        HistoricalCompanyFact(
            "operating_income",
            _number(text, r"([0-9.]+)\s+trillion won in operating profit", "operating profit"),
            "KRW_trillion",
        ),
        HistoricalCompanyFact(
            "net_income",
            _number(text, r"([0-9.]+)\s+trillion won in net profit", "net profit"),
            "KRW_trillion",
        ),
    )
    forward_start = date(2026, 4, 23)
    forward_end = date(2026, 6, 30)
    claims = (
        HistoricalForwardClaim(
            spec.ticker,
            "dram_total",
            "dram_asp_change",
            "Company expected favorable DRAM pricing conditions to continue after 1Q26.",
            forward_start,
            forward_end,
        ),
        HistoricalForwardClaim(
            spec.ticker,
            "dram_total",
            "dram_product_mix",
            "Company highlighted HBM and high-capacity server DRAM as high-value products.",
            forward_start,
            forward_end,
        ),
        HistoricalForwardClaim(
            spec.ticker,
            "hbm_mix_overlay",
            "hbm_yield",
            "Company identified HBM performance, yield, quality, and supply stability as capabilities to strengthen.",
            forward_start,
            forward_end,
        ),
        HistoricalForwardClaim(
            spec.ticker,
            "hbm_mix_overlay",
            "hbm_capacity",
            "Company stated customer demand exceeded supply capacity and tied investment to structural demand.",
            forward_start,
            forward_end,
        ),
        HistoricalForwardClaim(
            spec.ticker,
            "nand_and_solutions",
            "nand_asp_change",
            "Company expected favorable NAND pricing conditions to continue after 1Q26.",
            forward_start,
            forward_end,
        ),
        HistoricalForwardClaim(
            spec.ticker,
            "nand_and_solutions",
            "enterprise_ssd_mix",
            "Company planned to use its eSSD lineup and Solidigm synergies for AI storage demand.",
            forward_start,
            forward_end,
        ),
    )
    return ParsedHistoricalOfficialIr(
        spec=spec,
        source_document_sha256=hashlib.sha256(data).hexdigest(),
        visible_text=text,
        company_facts=facts,
        forward_claims=claims,
    )


def parse_historical_official_ir(
    spec: HistoricalOfficialIrSpec,
    data: bytes,
) -> ParsedHistoricalOfficialIr:
    if spec.parser_id == "skhynix_newsroom_2026q1_v1":
        return parse_skhynix_2026q1_newsroom(spec, data)
    raise ValueError(f"Historical official IR parser is not implemented: {spec.parser_id}")


__all__ = [
    "DEFAULT_HISTORICAL_IR_REGISTRY",
    "HistoricalCompanyFact",
    "HistoricalForwardClaim",
    "HistoricalOfficialIrSpec",
    "ParsedHistoricalOfficialIr",
    "extract_visible_html_text",
    "load_historical_official_ir_registry",
    "parse_historical_official_ir",
    "parse_skhynix_2026q1_newsroom",
]
