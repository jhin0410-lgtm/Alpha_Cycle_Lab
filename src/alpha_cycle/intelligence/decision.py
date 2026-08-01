"""Integrated investment-decision snapshots from immutable local source snapshots."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.decision_features import (
    build_macro_regime,
    build_market_context,
    classify_disclosures,
    extract_financial_kpis,
)
from alpha_cycle.intelligence.decision_scoring import (
    CompanyExposure,
    DecisionPolicy,
    build_report,
    build_scorecards,
)
from alpha_cycle.intelligence.valuation import (
    append_valuation_report,
    apply_valuation_to_scorecards,
)

DECISION_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class InvestmentDecisionSnapshot:
    """Content-addressed investment-decision evidence and conclusions."""

    captured_at: datetime
    evaluation_date: date
    research_snapshot_id: str
    market_snapshot_id: str
    valuation_snapshot_id: str | None
    policy: DecisionPolicy
    financial_kpis: pd.DataFrame
    financial_mapping: pd.DataFrame
    disclosure_events: pd.DataFrame
    catalysts: pd.DataFrame
    disclosure_summary: pd.DataFrame
    macro_regime: pd.DataFrame
    market_context: pd.DataFrame
    valuation_metrics: pd.DataFrame
    financial_history: pd.DataFrame
    scorecards: pd.DataFrame
    decision_records: pd.DataFrame
    report_markdown: str
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        _validate_snapshot_id(self.research_snapshot_id, "research_snapshot_id")
        _validate_snapshot_id(self.market_snapshot_id, "market_snapshot_id")
        if self.valuation_snapshot_id is not None:
            _validate_snapshot_id(self.valuation_snapshot_id, "valuation_snapshot_id")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": DECISION_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "research_snapshot_id": self.research_snapshot_id,
            "market_snapshot_id": self.market_snapshot_id,
            "valuation_snapshot_id": self.valuation_snapshot_id,
            "policy": {
                "recent_disclosure_days": self.policy.recent_disclosure_days,
                "positive_threshold": self.policy.positive_threshold,
                "mixed_threshold": self.policy.mixed_threshold,
                "minimum_coverage": self.policy.minimum_coverage,
            },
            "financial_kpis": _records(self.financial_kpis),
            "financial_mapping": _records(self.financial_mapping),
            "disclosure_events": _records(self.disclosure_events),
            "catalysts": _records(self.catalysts),
            "disclosure_summary": _records(self.disclosure_summary),
            "macro_regime": _records(self.macro_regime),
            "market_context": _records(self.market_context),
            "valuation_metrics": _records(self.valuation_metrics),
            "financial_history": _records(self.financial_history),
            "scorecards": _records(self.scorecards),
            "decision_records": _records(self.decision_records),
            "report_markdown": self.report_markdown,
            "warnings": list(self.warnings),
        }

    @property
    def snapshot_id(self) -> str:
        encoded = _canonical_json(self.payload_without_id()).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _json_value(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ValueError("Decision snapshot values must be finite")
        return value
    if isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Decision snapshot value is not serializable: {type(value).__name__}")


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _validate_snapshot_id(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def _read_json(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return cast(Mapping[str, object], payload)


def _snapshot_directory(path: str | Path) -> Path:
    result = Path(path)
    if not result.is_dir():
        raise ValueError(f"Snapshot directory does not exist: {result}")
    manifest = result / "manifest.json"
    if not manifest.is_file():
        raise ValueError(f"Snapshot manifest does not exist: {manifest}")
    return result


def _ticker_codes(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip()
    if values.isna().any() or values.eq("").any():
        raise ValueError("Ticker codes cannot be missing")
    if (~values.str.fullmatch(r"\d{1,6}")).any():
        raise ValueError("Ticker codes must contain one to six digits")
    return values.str.zfill(6)


def _symbol_codes(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip().str.upper()
    numeric = values.str.fullmatch(r"\d{1,6}")
    values.loc[numeric] = values.loc[numeric].str.zfill(6)
    if values.isna().any() or values.eq("").any():
        raise ValueError("Market symbols cannot be missing")
    return values


def _load_disclosures(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"ticker": "string", "rcept_no": "string"})
    if "ticker" not in frame.columns:
        raise ValueError("Disclosure CSV is missing ticker")
    frame["ticker"] = _ticker_codes(frame["ticker"])
    if "rcept_no" in frame.columns:
        frame["rcept_no"] = frame["rcept_no"].astype("string").str.zfill(14)
    return frame


def _load_market_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"symbol": "string"})
    if "symbol" not in frame.columns:
        raise ValueError(f"Market CSV is missing symbol: {path.name}")
    frame["symbol"] = _symbol_codes(frame["symbol"])
    return frame


def _filter_market_inputs(
    candles: pd.DataFrame,
    technical: pd.DataFrame,
    decision_tickers: set[str],
    *,
    benchmark: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    required = set(decision_tickers)
    if benchmark is not None:
        required.add(benchmark)
    available = set(candles["symbol"].astype(str))
    missing = sorted(required - available)
    if missing:
        raise ValueError(
            "Market snapshot is missing required decision symbols: "
            f"{','.join(missing)}"
        )
    extras = tuple(sorted(available - required))
    filtered_candles = candles.loc[candles["symbol"].isin(required)].copy()
    filtered_technical = technical.loc[technical["symbol"].isin(required)].copy()
    return filtered_candles, filtered_technical, extras


def _validate_ticker_sets(financial_kpis: pd.DataFrame, market_context: pd.DataFrame) -> None:
    financial = set(_ticker_codes(financial_kpis["ticker"]).astype(str))
    market = set(_ticker_codes(market_context["ticker"]).astype(str))
    if financial != market:
        raise ValueError(
            "Financial and market snapshot ticker sets differ: "
            f"financial={sorted(financial)}, market={sorted(market)}"
        )


def _load_valuation_snapshot(
    path: str | Path,
    *,
    research_snapshot_id: str,
    market_snapshot_id: str,
    evaluation_date: date,
) -> tuple[str, pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    directory = _snapshot_directory(path)
    manifest = _read_json(directory / "manifest.json")
    snapshot_id = str(manifest.get("snapshot_id", ""))
    _validate_snapshot_id(snapshot_id, "valuation_snapshot_id")
    if str(manifest.get("research_snapshot_id", "")) != research_snapshot_id:
        raise ValueError("Valuation snapshot is linked to a different research snapshot")
    if str(manifest.get("market_snapshot_id", "")) != market_snapshot_id:
        raise ValueError("Valuation snapshot is linked to a different market snapshot")
    if date.fromisoformat(str(manifest.get("evaluation_date", ""))) != evaluation_date:
        raise ValueError("Valuation snapshot evaluation date does not match")
    metrics = pd.read_csv(
        directory / "valuation_metrics.csv",
        dtype={"ticker": "string"},
    )
    history = pd.read_csv(
        directory / "financial_history.csv",
        dtype={"ticker": "string", "report_code": "string"},
    )
    if "ticker" not in metrics.columns or "ticker" not in history.columns:
        raise ValueError("Valuation snapshot files must contain ticker")
    metrics["ticker"] = _ticker_codes(metrics["ticker"])
    history["ticker"] = _ticker_codes(history["ticker"])
    warnings_value = manifest.get("warnings", [])
    warnings = (
        tuple(str(item) for item in warnings_value)
        if isinstance(warnings_value, list)
        else ()
    )
    return snapshot_id, metrics, history, warnings


def build_investment_decision_snapshot(
    research_snapshot: str | Path,
    market_snapshot: str | Path,
    *,
    valuation_snapshot: str | Path | None = None,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build one integrated decision snapshot from linked immutable snapshots."""

    decision_policy = policy or DecisionPolicy()
    research_dir = _snapshot_directory(research_snapshot)
    market_dir = _snapshot_directory(market_snapshot)
    research_manifest = _read_json(research_dir / "manifest.json")
    market_manifest = _read_json(market_dir / "manifest.json")
    research_id = str(research_manifest.get("snapshot_id", ""))
    market_id = str(market_manifest.get("snapshot_id", ""))
    _validate_snapshot_id(research_id, "research_snapshot_id")
    _validate_snapshot_id(market_id, "market_snapshot_id")
    linked_market_id = str(research_manifest.get("market_snapshot_id", ""))
    if linked_market_id and linked_market_id != market_id:
        raise ValueError("Research snapshot is linked to a different market snapshot")
    evaluation_date = date.fromisoformat(str(research_manifest.get("evaluation_date", "")))

    raw_opendart = _read_json(research_dir / "raw_opendart.json")
    financial_kpis, financial_mapping, financial_warnings = extract_financial_kpis(
        raw_opendart
    )
    financial_kpis["ticker"] = _ticker_codes(financial_kpis["ticker"])
    decision_tickers = set(financial_kpis["ticker"].astype(str))
    if not financial_mapping.empty:
        financial_mapping["ticker"] = _ticker_codes(financial_mapping["ticker"])

    disclosure_events, catalysts, disclosure_summary = classify_disclosures(
        _load_disclosures(research_dir / "disclosures.csv"),
        evaluation_date=evaluation_date,
        recent_days=decision_policy.recent_disclosure_days,
    )
    for frame in (disclosure_events, catalysts, disclosure_summary):
        if not frame.empty:
            frame["ticker"] = _ticker_codes(frame["ticker"])

    macro = pd.read_csv(research_dir / "macro.csv", dtype={"series_id": "string"})
    macro_regime = build_macro_regime(macro)
    candles, technical, extra_market_symbols = _filter_market_inputs(
        _load_market_csv(market_dir / "candles.csv"),
        _load_market_csv(market_dir / "technical_features.csv"),
        decision_tickers,
        benchmark=benchmark,
    )
    full_market_context = build_market_context(
        candles,
        technical,
        benchmark=benchmark,
    )
    full_market_context["ticker"] = _ticker_codes(full_market_context["ticker"])
    market_context = full_market_context.loc[
        full_market_context["ticker"].isin(decision_tickers)
    ].copy()
    _validate_ticker_sets(financial_kpis, market_context)

    exposure_map = dict(exposures or {})
    scorecards = build_scorecards(
        financial_kpis,
        disclosure_summary,
        macro_regime,
        market_context,
        exposure_map,
        decision_policy,
    )
    scorecards["ticker"] = _ticker_codes(scorecards["ticker"])

    valuation_id: str | None = None
    valuation_metrics = pd.DataFrame(columns=["ticker"])
    financial_history = pd.DataFrame(columns=["ticker"])
    valuation_warnings: tuple[str, ...] = ()
    if valuation_snapshot is not None:
        valuation_id, valuation_metrics, financial_history, valuation_warnings = (
            _load_valuation_snapshot(
                valuation_snapshot,
                research_snapshot_id=research_id,
                market_snapshot_id=market_id,
                evaluation_date=evaluation_date,
            )
        )
        valuation_tickers = set(valuation_metrics["ticker"].astype(str))
        score_tickers = set(scorecards["ticker"].astype(str))
        if valuation_tickers != score_tickers:
            raise ValueError(
                "Valuation and decision ticker sets differ: "
                f"valuation={sorted(valuation_tickers)}, decision={sorted(score_tickers)}"
            )
        scorecards = apply_valuation_to_scorecards(
            scorecards,
            valuation_metrics,
            decision_policy,
        )

    price_lookup = market_context.set_index("ticker")["last_price"].to_dict()
    decision_records = scorecards.loc[
        :,
        [
            "ticker",
            "decision_state",
            "action_bias",
            "composite_score",
            "score_coverage",
        ],
    ].copy()
    decision_records.insert(1, "evaluation_date", evaluation_date)
    decision_records.insert(2, "reference_price", decision_records["ticker"].map(price_lookup))
    if decision_records["reference_price"].isna().any():
        raise ValueError("Decision records are missing reference prices")

    warnings = [*financial_warnings]
    if extra_market_symbols:
        warnings.append(
            "market_snapshot_auxiliary_symbols_excluded_from_decision_context:"
            + ",".join(extra_market_symbols)
        )
    if valuation_id is None:
        warnings.append("valuation_and_consensus_not_available")
    else:
        warnings.extend(valuation_warnings)
        warnings.append("consensus_not_available")
    if not exposure_map:
        warnings.append("company_macro_exposures_not_configured")
    report = build_report(
        evaluation_date,
        scorecards,
        financial_kpis,
        catalysts,
        macro_regime,
        market_context,
        tuple(warnings),
    )
    if valuation_id is not None:
        report = append_valuation_report(report, valuation_metrics, financial_history)
    return InvestmentDecisionSnapshot(
        captured_at=now or datetime.now(UTC),
        evaluation_date=evaluation_date,
        research_snapshot_id=research_id,
        market_snapshot_id=market_id,
        valuation_snapshot_id=valuation_id,
        policy=decision_policy,
        financial_kpis=financial_kpis,
        financial_mapping=financial_mapping,
        disclosure_events=disclosure_events,
        catalysts=catalysts,
        disclosure_summary=disclosure_summary,
        macro_regime=macro_regime,
        market_context=market_context,
        valuation_metrics=valuation_metrics,
        financial_history=financial_history,
        scorecards=scorecards,
        decision_records=decision_records,
        report_markdown=report,
        warnings=tuple(warnings),
    )


def write_investment_decision_snapshot(
    output_root: str | Path,
    snapshot: InvestmentDecisionSnapshot,
) -> tuple[Path, ...]:
    """Atomically write one content-addressed decision-intelligence snapshot."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    names = (
        "manifest.json",
        "financial_kpis.csv",
        "financial_kpi_mapping.csv",
        "disclosure_events.csv",
        "catalysts.csv",
        "disclosure_summary.csv",
        "macro_regime.csv",
        "market_context.csv",
        "valuation_metrics.csv",
        "financial_history.csv",
        "scorecards.csv",
        "decision_records.csv",
        "report.md",
    )
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if manifest.get("snapshot_id") != snapshot.snapshot_id:
            raise ValueError("Existing decision snapshot conflicts with requested snapshot")
        return tuple(directory / name for name in names)

    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        frames = {
            "financial_kpis.csv": snapshot.financial_kpis,
            "financial_kpi_mapping.csv": snapshot.financial_mapping,
            "disclosure_events.csv": snapshot.disclosure_events,
            "catalysts.csv": snapshot.catalysts,
            "disclosure_summary.csv": snapshot.disclosure_summary,
            "macro_regime.csv": snapshot.macro_regime,
            "market_context.csv": snapshot.market_context,
            "valuation_metrics.csv": snapshot.valuation_metrics,
            "financial_history.csv": snapshot.financial_history,
            "scorecards.csv": snapshot.scorecards,
            "decision_records.csv": snapshot.decision_records,
        }
        for name, frame in frames.items():
            frame.to_csv(temporary / name, index=False)
        (temporary / "report.md").write_text(snapshot.report_markdown, encoding="utf-8")
        state_counts = {
            str(key): int(value)
            for key, value in snapshot.scorecards["decision_state"].value_counts().items()
        }
        manifest = {
            "schema_version": DECISION_SCHEMA_VERSION,
            "snapshot_id": snapshot.snapshot_id,
            "captured_at": snapshot.captured_at.isoformat(),
            "evaluation_date": snapshot.evaluation_date.isoformat(),
            "research_snapshot_id": snapshot.research_snapshot_id,
            "market_snapshot_id": snapshot.market_snapshot_id,
            "valuation_snapshot_id": snapshot.valuation_snapshot_id,
            "symbols": snapshot.scorecards["ticker"].astype(str).tolist(),
            "decision_states": state_counts,
            "warnings": list(snapshot.warnings),
            "valuation_available": snapshot.valuation_snapshot_id is not None,
            "valuation_scored_count": int(
                snapshot.scorecards["valuation_score"].notna().sum()
            ),
            "consensus_available": False,
            "order_api_enabled": False,
            "files": list(names[1:]),
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
