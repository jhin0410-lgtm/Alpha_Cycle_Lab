"""Synchronized OpenDART and ECOS intelligence snapshots."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from alpha_cycle.data.research import (
    FinancialStatementStore,
    MacroSeriesStore,
    ResearchDataPortal,
    RevisionPolicy,
)
from alpha_cycle.providers.ecos import EcosReadOnlyClient, EcosSeriesSpec
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

RESEARCH_INTELLIGENCE_SCHEMA_VERSION = 1


def _json_value(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for raw in frame.to_dict(orient="records"):
        records.append({str(key): _json_value(value) for key, value in raw.items()})
    return records


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _market_snapshot_id(path: Path | None) -> str | None:
    if path is None:
        return None
    manifest_path = path / "manifest.json" if path.is_dir() else path
    if not manifest_path.is_file():
        raise ValueError(f"Market snapshot manifest does not exist: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Market snapshot manifest must be an object")
    snapshot_id = str(payload.get("snapshot_id", "")).strip()
    if len(snapshot_id) != 64 or any(
        char not in "0123456789abcdef" for char in snapshot_id
    ):
        raise ValueError("Market snapshot manifest has an invalid snapshot_id")
    return snapshot_id


@dataclass(frozen=True)
class FundamentalMacroSnapshot:
    """Immutable PIT-visible financial, disclosure, and macro dataset."""

    captured_at: datetime
    evaluation_date: date
    revision_policy: RevisionPolicy
    financials: pd.DataFrame
    disclosures: pd.DataFrame
    macro: pd.DataFrame
    raw_opendart: object
    raw_ecos: object
    market_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if self.captured_at.date() < self.evaluation_date:
            raise ValueError("captured_at cannot precede evaluation_date")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": RESEARCH_INTELLIGENCE_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "revision_policy": self.revision_policy.value,
            "market_snapshot_id": self.market_snapshot_id,
            "financials": _records(self.financials),
            "disclosures": _records(self.disclosures),
            "macro": _records(self.macro),
            "raw_opendart": self.raw_opendart,
            "raw_ecos": self.raw_ecos,
        }

    @property
    def snapshot_id(self) -> str:
        encoded = _canonical_json(self.payload_without_id()).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class FundamentalMacroCollector:
    """Collect official fundamentals and macro data under one evaluation date."""

    def __init__(
        self,
        opendart: OpenDartReadOnlyClient,
        ecos: EcosReadOnlyClient,
    ) -> None:
        self.opendart = opendart
        self.ecos = ecos

    def collect(
        self,
        symbols: list[str] | tuple[str, ...],
        *,
        business_year: int,
        report_code: str,
        fs_div: str,
        disclosure_begin: date,
        disclosure_end: date,
        ecos_specs: tuple[EcosSeriesSpec, ...],
        evaluation_date: date,
        revision_policy: RevisionPolicy,
        market_snapshot: Path | None = None,
    ) -> FundamentalMacroSnapshot:
        resolved = self.opendart.resolve_stock_codes(symbols)
        financial_frames: list[pd.DataFrame] = []
        disclosure_frames: list[pd.DataFrame] = []
        raw_dart: dict[str, object] = {}
        captured_candidates: list[datetime] = []
        for symbol in sorted(resolved):
            corp = resolved[symbol]
            financial = self.opendart.financial_statements(
                corp,
                business_year=business_year,
                report_code=report_code,
                fs_div=fs_div,
            )
            disclosures = self.opendart.disclosures(
                corp,
                begin_date=disclosure_begin,
                end_date=disclosure_end,
            )
            financial_frames.append(financial.frame)
            disclosure_frames.append(disclosures.frame)
            raw_dart[symbol] = {
                "corp": {
                    "corp_code": corp.corp_code,
                    "corp_name": corp.corp_name,
                    "stock_code": corp.stock_code,
                    "modify_date": corp.modify_date.isoformat(),
                },
                "financial": financial.raw_payload,
                "disclosures": disclosures.raw_payload,
            }
            timestamps = pd.to_datetime(financial.frame["retrieved_at"], utc=True)
            captured_candidates.append(timestamps.max().to_pydatetime())
        financial_all = pd.concat(financial_frames, ignore_index=True)
        disclosure_all = pd.concat(disclosure_frames, ignore_index=True)
        macro_batch = self.ecos.collect(ecos_specs)
        macro_times = pd.to_datetime(macro_batch.frame["retrieved_at"], utc=True)
        captured_candidates.append(macro_times.max().to_pydatetime())
        portal = ResearchDataPortal(
            financials=FinancialStatementStore(financial_all),
            macro=MacroSeriesStore(macro_batch.frame),
            revision_policy=revision_policy,
        )
        visible = portal.snapshot(evaluation_date)
        visible_disclosures = disclosure_all.loc[
            disclosure_all["receipt_date"] <= evaluation_date
        ].sort_values(["ticker", "receipt_date", "rcept_no"], kind="stable")
        captured_at = max(captured_candidates).astimezone(UTC)
        return FundamentalMacroSnapshot(
            captured_at=captured_at,
            evaluation_date=evaluation_date,
            revision_policy=revision_policy,
            financials=visible.financials,
            disclosures=visible_disclosures.reset_index(drop=True),
            macro=visible.macro,
            raw_opendart=raw_dart,
            raw_ecos=dict(macro_batch.raw_payloads),
            market_snapshot_id=_market_snapshot_id(market_snapshot),
        )


def write_fundamental_macro_snapshot(
    output_root: str | Path,
    snapshot: FundamentalMacroSnapshot,
) -> tuple[Path, ...]:
    """Atomically write one content-addressed research-intelligence snapshot."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    names = (
        "manifest.json",
        "financials.csv",
        "disclosures.csv",
        "macro.csv",
        "raw_opendart.json",
        "raw_ecos.json",
    )
    if directory.exists():
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("snapshot_id") != snapshot.snapshot_id:
            raise ValueError("Existing research snapshot conflicts with requested snapshot")
        return tuple(directory / name for name in names)
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        snapshot.financials.to_csv(temporary / "financials.csv", index=False)
        snapshot.disclosures.to_csv(temporary / "disclosures.csv", index=False)
        snapshot.macro.to_csv(temporary / "macro.csv", index=False)
        (temporary / "raw_opendart.json").write_text(
            json.dumps(snapshot.raw_opendart, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (temporary / "raw_ecos.json").write_text(
            json.dumps(snapshot.raw_ecos, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": RESEARCH_INTELLIGENCE_SCHEMA_VERSION,
            "snapshot_id": snapshot.snapshot_id,
            "captured_at": snapshot.captured_at.isoformat(),
            "evaluation_date": snapshot.evaluation_date.isoformat(),
            "revision_policy": snapshot.revision_policy.value,
            "market_snapshot_id": snapshot.market_snapshot_id,
            "financial_rows": len(snapshot.financials),
            "disclosure_rows": len(snapshot.disclosures),
            "macro_rows": len(snapshot.macro),
            "availability_policy": {
                "opendart": "filing_receipt_date",
                "ecos": "retrieval_date_conservative",
            },
            "files": list(names[1:]),
            "order_api_enabled": False,
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return tuple(directory / name for name in names)
