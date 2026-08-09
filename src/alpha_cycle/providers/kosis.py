"""Read-only KOSIS discovery boundary for official industry-cycle evidence."""

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
    """Official KOSIS OpenAPI client used only for read-only source discovery."""

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
