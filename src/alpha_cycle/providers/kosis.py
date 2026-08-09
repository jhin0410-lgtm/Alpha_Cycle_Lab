"""Read-only KOSIS boundaries for official industry-cycle evidence."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlencode

from alpha_cycle.providers.read_only_http import (
    HttpBytesTransport,
    RetryingReadOnlyClient,
    decode_json,
)

KOSIS_BASE_URL = "https://kosis.kr/openapi"
DEFAULT_INDUSTRY_SEARCH = "품목별 광공업 생산·출하·재고·내수·수출량"
DEFAULT_KOSIS_ORG_ID = "101"
DEFAULT_KOSIS_TABLE_ID = "DT_1F02012"
DEFAULT_KOSIS_PERIOD = "M"
_SUPPORTED_PERIODS = {"D", "M", "Q", "S", "Y", "F", "IR"}


@dataclass(frozen=True)
class KosisCredentials:
    """KOSIS API key loaded only from the local environment."""

    api_key: str
    base_url: str = KOSIS_BASE_URL

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> KosisCredentials:
        values = os.environ if environ is None else environ
        api_key = values.get("KOSIS_API_KEY", "").strip()
        if not api_key:
            raise ValueError("KOSIS_API_KEY must be set locally")
        if "replace_with" in api_key.casefold():
            raise ValueError("KOSIS placeholder credentials cannot be used")
        return cls(api_key=api_key)

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != KOSIS_BASE_URL:
            raise ValueError("Only the official KOSIS OpenAPI host is allowed")


@dataclass(frozen=True)
class KosisTableCandidate:
    """Normalized KOSIS integrated-search table identity."""

    org_id: str
    org_name: str
    table_id: str
    table_name: str
    stat_id: str
    stat_name: str
    view_code: str
    location: str
    start_period: str
    end_period: str

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> KosisTableCandidate:
        candidate = cls(
            org_id=str(row.get("ORG_ID", "")).strip(),
            org_name=str(row.get("ORG_NM", "")).strip(),
            table_id=str(row.get("TBL_ID", "")).strip(),
            table_name=str(row.get("TBL_NM", "")).strip(),
            stat_id=str(row.get("STAT_ID", "")).strip(),
            stat_name=str(row.get("STAT_NM", "")).strip(),
            view_code=str(row.get("VW_CD", "")).strip(),
            location=str(row.get("MT_ATITLE", "")).strip(),
            start_period=str(row.get("STRT_PRD_DE", "")).strip(),
            end_period=str(row.get("END_PRD_DE", "")).strip(),
        )
        if not candidate.org_id or not candidate.table_id or not candidate.table_name:
            raise ValueError("KOSIS search row is missing table identity fields")
        return candidate


@dataclass(frozen=True)
class KosisTableIdentity:
    """A uniquely verified KOSIS table identity."""

    candidate: KosisTableCandidate
    exact_title_match: bool
    metadata_title_verified: bool

    @property
    def verified(self) -> bool:
        return self.exact_title_match and self.metadata_title_verified


@dataclass(frozen=True)
class KosisParameterQuery:
    """Explicit KOSIS parameter-data request with bounded time semantics."""

    org_id: str = DEFAULT_KOSIS_ORG_ID
    table_id: str = DEFAULT_KOSIS_TABLE_ID
    object_codes: tuple[str, ...] = ("ALL",)
    item_id: str = "ALL"
    period: str = DEFAULT_KOSIS_PERIOD
    start_period: str | None = None
    end_period: str | None = None
    latest_count: int | None = 1
    period_interval: int = 1

    def __post_init__(self) -> None:
        if not self.org_id.strip() or not self.table_id.strip():
            raise ValueError("KOSIS org_id and table_id are required")
        if not 1 <= len(self.object_codes) <= 8:
            raise ValueError("KOSIS object_codes must contain between 1 and 8 dimensions")
        if any(not code.strip() for code in self.object_codes):
            raise ValueError("KOSIS object_codes cannot contain blanks")
        if not self.item_id.strip():
            raise ValueError("KOSIS item_id cannot be blank")
        if self.period not in _SUPPORTED_PERIODS:
            raise ValueError(f"Unsupported KOSIS period: {self.period}")
        has_start = self.start_period is not None
        has_end = self.end_period is not None
        if has_start != has_end:
            raise ValueError("KOSIS start_period and end_period must be supplied together")
        if has_start and self.latest_count is not None:
            raise ValueError("KOSIS period range and latest_count are mutually exclusive")
        if self.latest_count is not None and self.latest_count <= 0:
            raise ValueError("KOSIS latest_count must be positive")
        if self.period_interval <= 0:
            raise ValueError("KOSIS period_interval must be positive")
        if self.period == "M" and has_start:
            assert self.start_period is not None
            assert self.end_period is not None
            _validate_month(self.start_period, field="start_period")
            _validate_month(self.end_period, field="end_period")
            if self.start_period > self.end_period:
                raise ValueError("KOSIS start_period cannot follow end_period")

    def params(self) -> dict[str, str]:
        params = {
            "method": "getList",
            "orgId": self.org_id.strip(),
            "tblId": self.table_id.strip(),
            "itmId": self.item_id.strip(),
            "prdSe": self.period,
            "prdInterval": str(self.period_interval),
            "format": "json",
            "jsonVD": "Y",
        }
        for index, code in enumerate(self.object_codes, start=1):
            params[f"objL{index}"] = code.strip()
        if self.start_period is not None and self.end_period is not None:
            params["startPrdDe"] = self.start_period
            params["endPrdDe"] = self.end_period
        elif self.latest_count is not None:
            params["newEstPrdCnt"] = str(self.latest_count)
        return params


@dataclass(frozen=True)
class KosisParameterRow:
    """Normalized identity fields from one KOSIS parameter-data observation."""

    org_id: str
    table_id: str
    table_name: str
    classification_ids: tuple[str, ...]
    classification_object_names: tuple[str, ...]
    classification_names: tuple[str, ...]
    item_id: str
    item_name: str
    unit_id: str
    unit_name: str
    period_type: str
    period: str
    value_text: str
    last_changed: str

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> KosisParameterRow:
        classification_ids: list[str] = []
        classification_object_names: list[str] = []
        classification_names: list[str] = []
        for index in range(1, 9):
            code = str(row.get(f"C{index}", "")).strip()
            object_name = str(row.get(f"C{index}_OBJ_NM", "")).strip()
            name = str(row.get(f"C{index}_NM", "")).strip()
            if code or object_name or name:
                classification_ids.append(code)
                classification_object_names.append(object_name)
                classification_names.append(name)

        normalized = cls(
            org_id=str(row.get("ORG_ID", "")).strip(),
            table_id=str(row.get("TBL_ID", "")).strip(),
            table_name=str(row.get("TBL_NM", "")).strip(),
            classification_ids=tuple(classification_ids),
            classification_object_names=tuple(classification_object_names),
            classification_names=tuple(classification_names),
            item_id=str(row.get("ITM_ID", "")).strip(),
            item_name=str(row.get("ITM_NM", "")).strip(),
            unit_id=str(row.get("UNIT_ID", "")).strip(),
            unit_name=str(row.get("UNIT_NM", "")).strip(),
            period_type=str(row.get("PRD_SE", "")).strip(),
            period=str(row.get("PRD_DE", "")).strip(),
            value_text=str(row.get("DT", "")).strip(),
            last_changed=str(row.get("LST_CHN_DE", "")).strip(),
        )
        required = (
            normalized.org_id,
            normalized.table_id,
            normalized.table_name,
            normalized.item_id,
            normalized.item_name,
            normalized.period_type,
            normalized.period,
        )
        if not all(required):
            raise ValueError("KOSIS parameter row is missing required identity fields")
        if not normalized.classification_ids or not normalized.classification_ids[0]:
            raise ValueError("KOSIS parameter row is missing first classification identity")
        return normalized

    @property
    def observation_key(self) -> tuple[tuple[str, ...], str, str]:
        return self.classification_ids, self.item_id, self.period


def _validate_month(value: str, *, field: str) -> None:
    if len(value) != 6 or not value.isdigit():
        raise ValueError(f"KOSIS {field} must use YYYYMM for monthly data")
    month = int(value[4:])
    if month < 1 or month > 12:
        raise ValueError(f"KOSIS {field} contains an invalid month")


def _rows(payload: object, *, service: str) -> tuple[Mapping[str, object], ...]:
    if isinstance(payload, dict):
        error_code = payload.get("err")
        if error_code is not None:
            message = str(payload.get("errMsg", "request failed")).strip()
            raise ValueError(f"KOSIS {service} failed: code={error_code} message={message}")
        raise ValueError(f"KOSIS {service} response must be an array")
    if not isinstance(payload, list):
        raise ValueError(f"KOSIS {service} response must be an array")
    normalized: list[Mapping[str, object]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError(f"KOSIS {service} row must be an object")
        normalized.append(cast(Mapping[str, object], raw))
    return tuple(normalized)


class KosisReadOnlyClient(RetryingReadOnlyClient):
    """Official KOSIS OpenAPI client used only for read-only research evidence."""

    def __init__(
        self,
        credentials: KosisCredentials,
        *,
        transport: HttpBytesTransport | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(
            transport=transport,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            sleep=sleep,
        )
        self.credentials = credentials

    @classmethod
    def from_env(cls) -> KosisReadOnlyClient:
        return cls(KosisCredentials.from_env())

    def _url(self, endpoint: str, params: Mapping[str, str]) -> str:
        query = urlencode({"apiKey": self.credentials.api_key, **dict(params)})
        return f"{self.credentials.base_url}/{endpoint}?{query}"

    def search_tables(
        self,
        search_name: str,
        *,
        org_id: str | None = DEFAULT_KOSIS_ORG_ID,
        sort: str = "RANK",
        result_count: int = 50,
    ) -> tuple[tuple[KosisTableCandidate, ...], object]:
        query = search_name.strip()
        if not query:
            raise ValueError("KOSIS search_name cannot be empty")
        if sort not in {"RANK", "DATE"}:
            raise ValueError("KOSIS sort must be RANK or DATE")
        if result_count <= 0 or result_count > 100:
            raise ValueError("KOSIS result_count must be between 1 and 100")
        params = {
            "method": "getList",
            "searchNm": query,
            "sort": sort,
            "startCount": "1",
            "resultCount": str(result_count),
            "format": "json",
            "content": "json",
            "jsonVD": "Y",
        }
        if org_id is not None:
            cleaned_org = org_id.strip()
            if not cleaned_org:
                raise ValueError("KOSIS org_id cannot be blank")
            params["orgId"] = cleaned_org
        response = self._get(self._url("statisticsSearch.do", params))
        if response.status != 200:
            raise ValueError(f"KOSIS HTTP {response.status}: service=statisticsSearch")
        payload = decode_json(response.body, provider="KOSIS")
        candidates = tuple(
            KosisTableCandidate.from_row(row)
            for row in _rows(payload, service="statisticsSearch")
        )
        return candidates, payload

    def table_title(self, org_id: str, table_id: str) -> tuple[str, object]:
        clean_org = org_id.strip()
        clean_table = table_id.strip()
        if not clean_org or not clean_table:
            raise ValueError("KOSIS org_id and table_id are required")
        response = self._get(
            self._url(
                "statisticsData.do",
                {
                    "method": "getMeta",
                    "type": "TBL",
                    "orgId": clean_org,
                    "tblId": clean_table,
                    "format": "json",
                    "content": "json",
                    "jsonVD": "Y",
                },
            )
        )
        if response.status != 200:
            raise ValueError(f"KOSIS HTTP {response.status}: service=tableMeta")
        payload = decode_json(response.body, provider="KOSIS")
        rows = _rows(payload, service="tableMeta")
        if len(rows) != 1:
            raise ValueError(f"KOSIS tableMeta must return exactly one row; got {len(rows)}")
        title = str(rows[0].get("TBL_NM", "")).strip()
        if not title:
            raise ValueError("KOSIS tableMeta returned an empty table title")
        return title, payload

    def fetch_parameter_data(
        self,
        query: KosisParameterQuery,
    ) -> tuple[tuple[KosisParameterRow, ...], object]:
        response = self._get(
            self._url("Param/statisticsParameterData.do", query.params())
        )
        if response.status != 200:
            raise ValueError(f"KOSIS HTTP {response.status}: service=parameterData")
        payload = decode_json(response.body, provider="KOSIS")
        rows = tuple(
            KosisParameterRow.from_row(row)
            for row in _rows(payload, service="parameterData")
        )
        if not rows:
            raise ValueError("KOSIS parameterData returned no observations")

        expected_org = query.org_id.strip()
        expected_table = query.table_id.strip()
        for row in rows:
            if row.org_id != expected_org or row.table_id != expected_table:
                raise ValueError("KOSIS parameterData returned mixed source identity")
            if row.period_type != query.period:
                raise ValueError("KOSIS parameterData returned an unexpected period type")

        keys = [row.observation_key for row in rows]
        if len(set(keys)) != len(keys):
            raise ValueError("KOSIS parameterData returned duplicate observation keys")
        return rows, payload

    def verify_exact_table(
        self,
        search_name: str = DEFAULT_INDUSTRY_SEARCH,
        *,
        org_id: str = DEFAULT_KOSIS_ORG_ID,
    ) -> tuple[KosisTableIdentity, object, object]:
        candidates, search_payload = self.search_tables(search_name, org_id=org_id)
        exact = tuple(candidate for candidate in candidates if candidate.table_name == search_name)
        if len(exact) != 1:
            raise ValueError(
                "KOSIS exact table discovery must resolve exactly one match: "
                f"query={search_name!r}, exact_matches={len(exact)}"
            )
        candidate = exact[0]
        metadata_title, metadata_payload = self.table_title(candidate.org_id, candidate.table_id)
        identity = KosisTableIdentity(
            candidate=candidate,
            exact_title_match=True,
            metadata_title_verified=metadata_title == candidate.table_name,
        )
        if not identity.verified:
            raise ValueError("KOSIS table metadata title does not match integrated-search identity")
        return identity, search_payload, metadata_payload
