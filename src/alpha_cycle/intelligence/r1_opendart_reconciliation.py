"""Fresh official reconciliation of exact reported fields, not blanket certification.

Archived responses can be reconstructed offline, but cannot authenticate their
own remote origin. Only this process's successful official retrieval supplies a
live verification; reading or copying a report does not restore that authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from weakref import WeakKeyDictionary

from alpha_cycle.intelligence.observable_universe import (
    ObservableUniverseSnapshot,
    _read_regular_file,
    _unique_object,
    _write_immutable,
)
from alpha_cycle.intelligence.r1_opendart_observations import (
    OpenDartFieldSelection,
    _build_opendart_universe,
)
from alpha_cycle.live_typed_source_revalidation_v2_1 import revalidate_research_snapshot
from alpha_cycle.providers.opendart import (
    REPORT_PERIODS,
    OpenDartCredentials,
    OpenDartReadOnlyClient,
)
from alpha_cycle.providers.read_only_http import HttpBytesResponse, UrllibReadOnlyTransport
from alpha_cycle.valuation_authority_v2_1 import (
    _opendart_statement_basis,
    _require_raw_actual_binding,
)


def _canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


@dataclass(frozen=True, eq=False)
class OpenDartFieldReconciliation:
    source_snapshot_id: str
    verified_at: datetime
    claims_json: str
    official_capture_json: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source_snapshot_id": self.source_snapshot_id,
            "verified_at": self.verified_at.isoformat(),
            "claims": json.loads(self.claims_json),
            "official_capture": json.loads(self.official_capture_json),
            "scope": "exact_reported_thstrm_amount_only",
            "offline_origin_authentication": False,
        }

    @property
    def content_id(self) -> str:
        return hashlib.sha256(_canonical(self.payload()).encode()).hexdigest()

    @property
    def fresh_official_verification(self) -> bool:
        return _LIVE_VERIFICATIONS.get(self) == self.content_id


_LIVE_VERIFICATIONS: WeakKeyDictionary[OpenDartFieldReconciliation, str] = WeakKeyDictionary()


class _NoAuthorityRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise ValueError("official authority retrieval rejects redirects")


class _OfficialOpenDartTransport(UrllibReadOnlyTransport):
    """Pin remote origin, including redirect handling, at the authority boundary."""

    def get(
        self, url: str, *, headers: Mapping[str, str], timeout_seconds: float,
    ) -> HttpBytesResponse:
        target = urlsplit(url)
        if (target.scheme, target.netloc) != ("https", "opendart.fss.or.kr"):
            raise ValueError("official authority retrieval requires the pinned HTTPS origin")
        request = Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate", **dict(headers),
        }, method="GET")
        try:
            with build_opener(_NoAuthorityRedirect()).open(
                request, timeout=timeout_seconds
            ) as response:
                if response.geturl() != url:
                    raise ValueError("official response URL differs from requested URL")
                response_headers = self._headers(response.headers)
                return HttpBytesResponse(
                    int(response.status), response_headers,
                    self._decompress(response.read(), response_headers),
                )
        except HTTPError as exc:
            response_headers = self._headers(exc.headers)
            try:
                return HttpBytesResponse(
                    int(exc.code), response_headers, self._decompress(exc.read(), response_headers)
                )
            except (HTTPException, EOFError) as body_error:
                raise OSError("official authority response was interrupted") from body_error
        except (URLError, TimeoutError, HTTPException, EOFError) as exc:
            raise OSError("official authority network request failed") from exc


def reconcile_opendart_capture(
    research_directory: str | Path,
    *,
    selections: tuple[OpenDartFieldSelection, ...],
    official_capture: dict[str, object],
    verified_at: datetime,
) -> OpenDartFieldReconciliation:
    """Check exact raw agreement; caller-provided captures remain unauthenticated.

    Used for offline reproduction and synthetic tests. It deliberately does not
    issue live authority, even if a caller supplies official-looking data.
    """
    source = revalidate_research_snapshot(research_directory)
    universe = _build_opendart_universe(
        source, selections=selections, universe_id="opendart-reconciliation",
        version="1", cutoff_at=verified_at,
    )
    claims: list[dict[str, object]] = []
    for selection in selections:
        # Universe observations are canonically sorted, so match by identity,
        # not the caller's selection order.
        observation = next(item for item in universe.observations if (
            item.member_id == selection.security_id
            and item.dimension_id == selection.dimension_id
        ))
        if _opendart_statement_basis(official_capture, selection.security_id) != (
            selection.statement_basis
        ):
            raise ValueError("official statement basis differs from selected field")
        rows = source.financials.loc[
            source.financials["ticker"].astype(str).eq(selection.security_id)
            & source.financials["metric"].astype(str).eq(selection.metric_id)
            & source.financials["period_end"].astype(str).eq(selection.period_end.isoformat())
            & source.financials["fiscal_period"].astype(str).eq(selection.fiscal_period)
            & source.financials["source"].astype(str).eq("opendart")
        ]
        if len(rows) != 1:
            raise ValueError("selected field is not unique")
        row = rows.iloc[0]
        _require_raw_actual_binding(official_capture, selection.security_id, row)
        claims.append({
            "observation_id": observation.observation_id,
            "evidence_reference_id": observation.evidence[0].reference_id,
            "security_id": selection.security_id,
            "metric_id": selection.metric_id,
            "period_end": selection.period_end.isoformat(),
            "fiscal_period": selection.fiscal_period,
            "basis": selection.statement_basis,
            "value": observation.value,
            "unit": observation.unit,
            "semantics": observation.semantics,
            "window": observation.window,
            "filing_receipt": str(row["revision_id"]),
            "source_available_at": observation.available_at.isoformat(),
            "authority_available_at": verified_at.isoformat(),
        })
    return OpenDartFieldReconciliation(
        source.snapshot_id, verified_at, _canonical(claims), _canonical(official_capture)
    )


def verify_opendart_reported_fields(
    research_directory: str | Path,
    *,
    selections: tuple[OpenDartFieldSelection, ...],
) -> OpenDartFieldReconciliation:
    """Re-fetch the official company and filing and verify exact selected claims.

    No transport, provider ID, certification flag or historical verification
    timestamp can be supplied by the caller. API credentials stay in the client.
    Revisions with a different receipt/value fail rather than rewriting history.
    """
    started = datetime.now(UTC)
    original = revalidate_research_snapshot(research_directory)
    _build_opendart_universe(
        original, selections=selections, universe_id="opendart-reconciliation",
        version="1", cutoff_at=started,
    )
    scopes = {(item.security_id, item.period_end.year, item.fiscal_period,
               item.statement_basis) for item in selections}
    if len({scope[0] for scope in scopes}) != len(scopes):
        raise ValueError("one filing scope per security is required per reconciliation")
    client = OpenDartReadOnlyClient(
        OpenDartCredentials.from_env(), transport=_OfficialOpenDartTransport(),
        timeout_seconds=20, max_retries=1,
    )
    resolved = client.resolve_stock_codes(sorted({item.security_id for item in selections}))
    capture: dict[str, object] = {}
    for security, year, fiscal_period, basis in sorted(scopes):
        codes = [key for key, value in REPORT_PERIODS.items() if value[0] == fiscal_period]
        if len(codes) != 1:
            raise ValueError("unsupported filing period")
        corp = resolved[security]
        batch = client.financial_statements(
            corp, business_year=year, report_code=codes[0], fs_div=basis
        )
        capture[security] = {
            "request": {"business_year": year, "report_code": codes[0], "fs_div": basis},
            "corp": {"corp_code": corp.corp_code, "stock_code": corp.stock_code},
            "financial": batch.raw_payload,
        }
    result = reconcile_opendart_capture(
        research_directory, selections=selections, official_capture=capture,
        verified_at=datetime.now(UTC),
    )
    if result.source_snapshot_id != original.snapshot_id:
        raise ValueError("source generation changed during official retrieval")
    _LIVE_VERIFICATIONS[result] = result.content_id
    return result


def require_reconciled_universe(
    result: OpenDartFieldReconciliation, universe: ObservableUniverseSnapshot,
) -> None:
    """Verify exact field/scope coverage at the consumer's PIT boundary."""
    if not result.fresh_official_verification:
        raise ValueError("fresh official verification is required")
    if result.verified_at > universe.research_cutoff_at:
        raise ValueError("official verification exceeds research cutoff")
    claims = json.loads(result.claims_json)
    expected = {(item["observation_id"], item["evidence_reference_id"]) for item in claims}
    actual = {(item.observation_id, ref.reference_id)
              for item in universe.observations for ref in item.evidence}
    if expected != actual or len(claims) != len(universe.observations):
        raise ValueError("official claims do not exactly cover current observations")


def persist_opendart_reconciliation(
    result: OpenDartFieldReconciliation, directory: str | Path,
) -> Path:
    """Store evidence bytes without serializing the process-local live authority."""
    root = Path(directory)
    path = root / f"{result.content_id}.json"
    content = _canonical({**result.payload(), "content_id": result.content_id})
    _write_immutable(path, content.encode("utf-8"))
    return path


def replay_opendart_reconciliation(
    path: str | Path, research_directory: str | Path,
    *, selections: tuple[OpenDartFieldSelection, ...],
) -> OpenDartFieldReconciliation:
    """Reconstruct stored agreement; remote-origin authentication stays false."""
    payload = json.loads(
        _read_regular_file(Path(path), "reconciliation artifact"), object_pairs_hook=_unique_object
    )
    if not isinstance(payload, dict):
        raise ValueError("reconciliation payload must be an object")
    if not isinstance(payload.get("official_capture"), dict) or not isinstance(
        payload.get("verified_at"), str
    ):
        raise ValueError("reconciliation capture and verification time are required")
    result = reconcile_opendart_capture(
        research_directory, selections=selections,
        official_capture=payload["official_capture"],
        verified_at=datetime.fromisoformat(payload["verified_at"]),
    )
    if payload != {**result.payload(), "content_id": result.content_id}:
        raise ValueError("reconciliation reconstruction mismatch")
    return result
