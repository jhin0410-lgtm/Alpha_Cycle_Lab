"""Read-only Bank of Korea ECOS macroeconomic-series adapter."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

from alpha_cycle.data.research import validate_macro_series
from alpha_cycle.providers.read_only_http import (
    HttpBytesTransport,
    RetryingReadOnlyClient,
    decode_json,
)

ECOS_BASE_URL = "https://ecos.bok.or.kr/api"
SUPPORTED_CYCLES = frozenset({"A", "Q", "M", "D"})
KOREA_TZ = ZoneInfo("Asia/Seoul")
MAX_ECOS_ROWS = 100000


@dataclass(frozen=True)
class EcosCredentials:
    """ECOS key loaded only from local environment variables."""

    api_key: str
    base_url: str = ECOS_BASE_URL

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> EcosCredentials:
        values = os.environ if environ is None else environ
        api_key = values.get("ECOS_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ECOS_API_KEY must be set locally")
        if "replace_with" in api_key.lower():
            raise ValueError("ECOS placeholder credentials cannot be used")
        return cls(api_key=api_key)

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != ECOS_BASE_URL:
            raise ValueError("Only the official Bank of Korea ECOS API host is allowed")


@dataclass(frozen=True)
class EcosSeriesSpec:
    """One explicit ECOS StatisticSearch request."""

    series_id: str
    stat_code: str
    cycle: str
    start: str
    end: str
    item_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.series_id.strip() or not self.stat_code.strip():
            raise ValueError("ECOS series_id and stat_code are required")
        if self.cycle not in SUPPORTED_CYCLES:
            raise ValueError("ECOS cycle must be one of A, Q, M, D")
        if not self.start.strip() or not self.end.strip():
            raise ValueError("ECOS start and end are required")
        if len(self.item_codes) > 4:
            raise ValueError("ECOS supports at most four item-code path segments")
        if any(not item.strip() for item in self.item_codes):
            raise ValueError("ECOS item codes cannot be empty")
        start_date = _observation_date(self.cycle, self.start)
        end_date = _observation_date(self.cycle, self.end)
        if start_date > end_date:
            raise ValueError("ECOS start cannot follow end")


@dataclass(frozen=True)
class EcosBatch:
    frame: pd.DataFrame
    raw_payloads: Mapping[str, object]


def _observation_date(cycle: str, value: object) -> date:
    text = str(value).strip().upper()
    formats = {"D": "%Y%m%d", "M": "%Y%m", "A": "%Y"}
    if cycle in formats:
        try:
            parsed = datetime.strptime(text, formats[cycle]).date()
        except ValueError as exc:
            raise ValueError(f"ECOS TIME is invalid for cycle {cycle}: {text}") from exc
        if cycle == "M":
            return parsed.replace(day=1)
        return parsed
    if cycle == "Q" and len(text) == 6 and text[4] == "Q" and text[5] in "1234":
        quarter = int(text[5])
        return date(int(text[:4]), 1 + (quarter - 1) * 3, 1)
    raise ValueError(f"ECOS TIME is invalid for cycle {cycle}: {text}")


def _optional_decimal(value: object) -> Decimal | None:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        return None
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"ECOS DATA_VALUE is invalid: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("ECOS DATA_VALUE must be finite")
    return result


def _result_error(container: Mapping[str, object], service: str) -> None:
    result = container.get("RESULT")
    if not isinstance(result, dict):
        return
    code = str(result.get("CODE", "unknown")).strip()
    message = str(result.get("MESSAGE", "request failed")).strip()
    raise ValueError(f"ECOS {service} failed: code={code} message={message}")


def _safe_int(value: object, field: str) -> int:
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"ECOS {field} must be an integer") from exc


def load_ecos_series_config(path: str | Path) -> tuple[EcosSeriesSpec, ...]:
    """Load explicit ECOS series requests from a local YAML file."""

    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError("ECOS config must be an object")
    series_raw = payload.get("series")
    if not isinstance(series_raw, list):
        raise ValueError("ECOS config must contain a series list")
    specs: list[EcosSeriesSpec] = []
    for raw in series_raw:
        if not isinstance(raw, dict):
            raise ValueError("Each ECOS series config entry must be an object")
        item_codes_raw = raw.get("item_codes", [])
        if not isinstance(item_codes_raw, list):
            raise ValueError("ECOS item_codes must be a list")
        specs.append(
            EcosSeriesSpec(
                series_id=str(raw.get("series_id", "")).strip(),
                stat_code=str(raw.get("stat_code", "")).strip(),
                cycle=str(raw.get("cycle", "")).strip().upper(),
                start=str(raw.get("start", "")).strip(),
                end=str(raw.get("end", "")).strip(),
                item_codes=tuple(str(item).strip() for item in item_codes_raw),
            )
        )
    if not specs:
        raise ValueError("ECOS config must include at least one series")
    ids = [spec.series_id for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("ECOS series_id values must be unique")
    return tuple(specs)


class EcosReadOnlyClient(RetryingReadOnlyClient):
    """Official ECOS StatisticSearch adapter with conservative PIT availability."""

    def __init__(
        self,
        credentials: EcosCredentials,
        *,
        transport: HttpBytesTransport | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__(
            transport=transport,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            sleep=sleep,
        )
        self.credentials = credentials
        self.now = now

    @classmethod
    def from_env(cls) -> EcosReadOnlyClient:
        return cls(EcosCredentials.from_env())

    def _url(self, spec: EcosSeriesSpec) -> str:
        segments = [
            "StatisticSearch",
            self.credentials.api_key,
            "json",
            "kr",
            "1",
            str(MAX_ECOS_ROWS),
            spec.stat_code,
            spec.cycle,
            spec.start,
            spec.end,
            *spec.item_codes,
        ]
        encoded = "/".join(quote(segment, safe="") for segment in segments)
        return f"{self.credentials.base_url}/{encoded}"

    def _validate_row_identity(
        self,
        raw: Mapping[str, object],
        spec: EcosSeriesSpec,
    ) -> None:
        returned_stat = str(raw.get("STAT_CODE", "")).strip()
        if returned_stat and returned_stat != spec.stat_code:
            raise ValueError(
                "ECOS response STAT_CODE does not match request: "
                f"expected={spec.stat_code}, actual={returned_stat}"
            )
        for index, expected in enumerate(spec.item_codes, start=1):
            returned = str(raw.get(f"ITEM_CODE{index}", "")).strip()
            if returned and returned != expected:
                raise ValueError(
                    "ECOS response item code does not match request: "
                    f"series_id={spec.series_id}, item={index}, "
                    f"expected={expected}, actual={returned}"
                )

    def search(self, spec: EcosSeriesSpec) -> tuple[pd.DataFrame, object]:
        response = self._get(self._url(spec))
        if response.status != 200:
            raise ValueError(f"ECOS HTTP {response.status}: service=StatisticSearch")
        payload = decode_json(response.body, provider="ECOS")
        if not isinstance(payload, dict):
            raise ValueError("ECOS response must be an object")
        root = cast(Mapping[str, object], payload)
        _result_error(root, "StatisticSearch")
        service = root.get("StatisticSearch")
        if not isinstance(service, dict):
            raise ValueError("ECOS StatisticSearch response is missing")
        rows_raw = service.get("row")
        if not isinstance(rows_raw, list):
            raise ValueError("ECOS StatisticSearch row must be an array")
        total_count = _safe_int(service.get("list_total_count", len(rows_raw)), "list_total_count")
        if total_count > len(rows_raw):
            raise ValueError(
                "ECOS response was truncated; narrow the configured date range "
                f"(total_count={total_count}, returned={len(rows_raw)})"
            )
        retrieved_at = self.now()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("ECOS client clock must be timezone-aware")
        available_date = retrieved_at.astimezone(KOREA_TZ).date()
        rows: list[dict[str, object]] = []
        seen_dates: set[date] = set()
        skipped_missing = 0
        for raw_value in rows_raw:
            if not isinstance(raw_value, dict):
                raise ValueError("ECOS StatisticSearch row must be an object")
            raw = cast(Mapping[str, object], raw_value)
            self._validate_row_identity(raw, spec)
            observation = _observation_date(spec.cycle, raw.get("TIME"))
            if observation in seen_dates:
                raise ValueError(
                    "ECOS series contains duplicate TIME values; configure enough item_codes: "
                    f"series_id={spec.series_id}, time={observation}"
                )
            value = _optional_decimal(raw.get("DATA_VALUE"))
            if value is None:
                skipped_missing += 1
                continue
            seen_dates.add(observation)
            unit = str(raw.get("UNIT_NAME", "")).strip() or "unspecified"
            revision_material = (
                f"{spec.series_id}|{observation.isoformat()}|{value}|{unit}|"
                f"{'|'.join(spec.item_codes)}"
            )
            rows.append(
                {
                    "series_id": spec.series_id,
                    "observation_date": observation,
                    "frequency": spec.cycle,
                    "value": value,
                    "unit": unit,
                    "available_date": available_date,
                    "retrieved_at": retrieved_at,
                    "source": "ecos",
                    "revision_id": hashlib.sha256(
                        revision_material.encode("utf-8")
                    ).hexdigest(),
                    "revision_sequence": 0,
                }
            )
        if not rows:
            raise ValueError(
                f"ECOS returned no numeric rows for series {spec.series_id}; "
                f"skipped_missing_values={skipped_missing}"
            )
        return validate_macro_series(pd.DataFrame(rows)), payload

    def collect(self, specs: Sequence[EcosSeriesSpec]) -> EcosBatch:
        if not specs:
            raise ValueError("At least one ECOS series specification is required")
        frames: list[pd.DataFrame] = []
        raw: dict[str, object] = {}
        for spec in specs:
            frame, payload = self.search(spec)
            frames.append(frame)
            raw[spec.series_id] = payload
        combined = validate_macro_series(pd.concat(frames, ignore_index=True))
        return EcosBatch(frame=combined, raw_payloads=raw)
