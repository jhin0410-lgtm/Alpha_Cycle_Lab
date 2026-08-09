"""One-command live market, research, valuation, and decision pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from alpha_cycle.data.research import RevisionPolicy
from alpha_cycle.intelligence import (
    CompanySecurityMapping,
    DecisionPolicy,
    FundamentalMacroCollector,
    MarketIntelligenceCollector,
    build_investment_decision_snapshot,
    build_valuation_evidence_snapshot,
    load_company_exposures,
    write_fundamental_macro_snapshot,
    write_investment_decision_snapshot,
    write_market_intelligence_snapshot,
    write_valuation_evidence_snapshot,
)
from alpha_cycle.providers import (
    EcosCredentials,
    EcosReadOnlyClient,
    EcosSeriesSpec,
    OpenDartCredentials,
    OpenDartReadOnlyClient,
    OpenDartValuationClient,
    TossInvestReadOnlyClient,
)

KOREA_TZ = ZoneInfo("Asia/Seoul")
PUBLIC_IP_ENDPOINT = "https://api.ipify.org"
DEFAULT_DECISION_SYMBOLS = ("005930", "000660")
DEFAULT_MARKET_SYMBOLS = ("005930", "005935", "000660")
DEFAULT_OUTPUT_ROOT = Path("data/private/live-research")
DEFAULT_INVESTOR_FLOW_POINTER = Path(
    "data/private/live-research/kiwoom-openapi-plus-investor-flow/"
    "latest_investor_flow_export.json"
)
T = TypeVar("T")


@dataclass(frozen=True)
class PipelineStageError(Exception):
    """Attach a stable stage name to an expected pipeline failure."""

    stage: str
    cause: Exception

    def __str__(self) -> str:
        return f"{self.stage}: {self.cause}"


class _SecurityClassSymbols(Mapping[str, str]):
    """Resolve OpenDART Korean security names through normalized class labels."""

    def __init__(self, class_symbols: Mapping[str, str]) -> None:
        allowed = {"common", "preferred", "other"}
        invalid = set(class_symbols) - allowed
        if invalid:
            raise ValueError(f"Unsupported security classes: {sorted(invalid)}")
        self._class_symbols = dict(class_symbols)

    @staticmethod
    def _security_class(name: object) -> str:
        text = str(name).strip().casefold().replace(" ", "")
        if "보통" in text or "common" in text:
            return "common"
        if "우선" in text or "preferred" in text:
            return "preferred"
        return "other"

    def __contains__(self, key: object) -> bool:
        return self._security_class(key) in self._class_symbols

    def __getitem__(self, key: str) -> str:
        return self._class_symbols[self._security_class(key)]

    def __iter__(self) -> Iterator[str]:
        return iter(self._class_symbols)

    def __len__(self) -> int:
        return len(self._class_symbols)


def _default_security_mappings() -> dict[str, CompanySecurityMapping]:
    return {
        "005930": CompanySecurityMapping(
            _SecurityClassSymbols(
                {
                    "common": "005930",
                    "preferred": "005935",
                }
            )
        ),
        "000660": CompanySecurityMapping(
            _SecurityClassSymbols({"common": "000660"})
        ),
    }


def _default_ecos_specs(
    evaluation_date: date,
    *,
    lookback_days: int,
) -> tuple[EcosSeriesSpec, ...]:
    if lookback_days <= 0:
        raise ValueError("--macro-lookback-days must be positive")
    start = (evaluation_date - timedelta(days=lookback_days)).strftime("%Y%m%d")
    end = evaluation_date.strftime("%Y%m%d")
    return (
        EcosSeriesSpec(
            series_id="kr_base_rate",
            stat_code="722Y001",
            cycle="D",
            start=start,
            end=end,
            item_codes=("0101000",),
        ),
        EcosSeriesSpec(
            series_id="usd_krw",
            stat_code="731Y001",
            cycle="D",
            start=start,
            end=end,
            item_codes=("0000001",),
        ),
    )


def _public_ip(timeout_seconds: float = 4.0) -> str | None:
    """Best-effort public-IP lookup used only after an allowlist rejection."""

    request = Request(
        PUBLIC_IP_ENDPOINT,
        headers={"User-Agent": "Alpha-Cycle-Lab/0.1 public-ip-diagnostic"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            value = response.read(128).decode("ascii", errors="strict").strip()
    except (OSError, UnicodeError, ValueError):
        return None
    parts = value.split(".")
    if len(parts) != 4:
        return None
    try:
        octets = [int(part) for part in parts]
    except ValueError:
        return None
    return value if all(0 <= item <= 255 for item in octets) else None


def _is_ip_allowlist_error(error: object) -> bool:
    text = str(error).casefold()
    return (
        "ip address not allowed" in text
        or "ip not allowed" in text
        or "allowlist" in text and "ip" in text
    )


def _write_status(output_root: Path, payload: Mapping[str, object]) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / "latest_run.json"
    temporary = output_root / ".latest_run.json.tmp"
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def _run_stage(stage: str, operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (ValueError, OSError, TypeError) as exc:
        raise PipelineStageError(stage, exc) from exc


def _flow_status(scorecards: Any) -> dict[str, object]:
    columns = set(scorecards.columns)
    if "investor_flow_evidence_verified" not in columns:
        return {
            "investor_flow_available": False,
            "investor_flow_evidence_verified": False,
            "investor_flow_score_enabled": False,
        }
    verified_values = scorecards["investor_flow_evidence_verified"].astype(bool)
    snapshot_values = scorecards["investor_flow_snapshot_id"].dropna().astype(str).unique()
    return {
        "investor_flow_available": True,
        "investor_flow_evidence_verified": bool(verified_values.all()),
        "investor_flow_score_enabled": False,
        "investor_flow_snapshot_id": (
            str(snapshot_values[0]) if len(snapshot_values) == 1 else None
        ),
    }


def _execute(args: argparse.Namespace) -> dict[str, object]:
    evaluation_date: date = args.evaluation_date or datetime.now(KOREA_TZ).date()
    if evaluation_date > datetime.now(KOREA_TZ).date():
        raise PipelineStageError(
            "validation",
            ValueError("--evaluation-date cannot be in the future"),
        )
    business_year = args.business_year or evaluation_date.year - 1
    disclosure_begin = evaluation_date - timedelta(days=args.disclosure_lookback_days)
    output_root: Path = args.output

    toss = TossInvestReadOnlyClient.from_env()
    toss.timeout_seconds = args.timeout_seconds
    toss.max_retries = args.max_retries
    market_snapshot = _run_stage(
        "market",
        lambda: MarketIntelligenceCollector(toss).collect(
            DEFAULT_MARKET_SYMBOLS,
            interval="1d",
            count=args.candle_count,
            adjusted=True,
        ),
    )
    market_files = _run_stage(
        "market_write",
        lambda: write_market_intelligence_snapshot(
            output_root / "market-intelligence",
            market_snapshot,
        ),
    )
    market_directory = market_files[0].parent

    opendart = OpenDartReadOnlyClient.from_env()
    ecos = EcosReadOnlyClient(EcosCredentials.from_env())
    for client in (opendart, ecos):
        client.timeout_seconds = args.timeout_seconds
        client.max_retries = args.max_retries
    research_snapshot = _run_stage(
        "research",
        lambda: FundamentalMacroCollector(opendart, ecos).collect(
            DEFAULT_DECISION_SYMBOLS,
            business_year=business_year,
            report_code="11011",
            fs_div="CFS",
            disclosure_begin=disclosure_begin,
            disclosure_end=evaluation_date,
            ecos_specs=_default_ecos_specs(
                evaluation_date,
                lookback_days=args.macro_lookback_days,
            ),
            evaluation_date=evaluation_date,
            revision_policy=RevisionPolicy.LATEST_KNOWN,
            market_snapshot=market_directory,
        ),
    )
    research_files = _run_stage(
        "research_write",
        lambda: write_fundamental_macro_snapshot(
            output_root / "research-intelligence",
            research_snapshot,
        ),
    )
    research_directory = research_files[0].parent

    valuation_client = OpenDartValuationClient(
        OpenDartCredentials.from_env(),
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
    )
    valuation_snapshot = _run_stage(
        "valuation",
        lambda: build_valuation_evidence_snapshot(
            research_directory,
            market_directory,
            valuation_client,
            history_years=args.history_years,
            fs_div="CFS",
            security_mappings=_default_security_mappings(),
        ),
    )
    valuation_files = _run_stage(
        "valuation_write",
        lambda: write_valuation_evidence_snapshot(
            output_root / "valuation-intelligence",
            valuation_snapshot,
        ),
    )
    valuation_directory = valuation_files[0].parent

    company_config = Path("config/company_exposures.local.yaml")
    exposures = load_company_exposures(company_config if company_config.is_file() else None)
    flow_pointer = (
        DEFAULT_INVESTOR_FLOW_POINTER
        if DEFAULT_INVESTOR_FLOW_POINTER.is_file()
        else None
    )
    decision_snapshot = _run_stage(
        "decision",
        lambda: build_investment_decision_snapshot(
            research_directory,
            market_directory,
            valuation_snapshot=valuation_directory,
            investor_flow_pointer=flow_pointer,
            exposures=exposures,
            policy=DecisionPolicy(),
        ),
    )
    decision_files = _run_stage(
        "decision_write",
        lambda: write_investment_decision_snapshot(
            output_root / "decision-intelligence",
            decision_snapshot,
        ),
    )
    decision_directory = decision_files[0].parent

    valuation_frame = valuation_snapshot.valuation_metrics
    scorecards = decision_snapshot.scorecards
    return {
        "status": "completed",
        "evaluation_date": evaluation_date.isoformat(),
        "decision_symbols": list(DEFAULT_DECISION_SYMBOLS),
        "market_symbols": list(DEFAULT_MARKET_SYMBOLS),
        "market_snapshot_id": market_snapshot.snapshot_id,
        "research_snapshot_id": research_snapshot.snapshot_id,
        "valuation_snapshot_id": valuation_snapshot.snapshot_id,
        "decision_snapshot_id": decision_snapshot.snapshot_id,
        "market_directory": str(market_directory.resolve()),
        "research_directory": str(research_directory.resolve()),
        "valuation_directory": str(valuation_directory.resolve()),
        "decision_directory": str(decision_directory.resolve()),
        "report_path": str((decision_directory / "report.md").resolve()),
        "market_cap_complete_count": int(
            valuation_frame["market_cap_complete"].astype(bool).sum()
        ),
        "valuation_scored_count": int(valuation_frame["valuation_score"].notna().sum()),
        "decision_states": {
            str(key): int(value)
            for key, value in scorecards["decision_state"].value_counts().items()
        },
        **_flow_status(scorecards),
        "warnings": list(decision_snapshot.warnings),
        "order_api_enabled": False,
    }


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-live",
        description=(
            "Run the Samsung Electronics, Samsung Electronics preferred, and SK hynix "
            "official-data research pipeline in one command"
        ),
    )
    parser.add_argument("--evaluation-date", type=_date_argument)
    parser.add_argument("--business-year", type=int)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--candle-count", type=int, default=100)
    parser.add_argument("--history-years", type=int, default=3)
    parser.add_argument("--macro-lookback-days", type=int, default=31)
    parser.add_argument("--disclosure-lookback-days", type=int, default=365)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument(
        "--no-public-ip-lookup",
        action="store_true",
        help="do not query api.ipify.org after a TossInvest IP allowlist rejection",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if args.business_year is not None and args.business_year < 2015:
        raise ValueError("--business-year must be 2015 or later")
    if args.candle_count <= 0 or args.candle_count > 200:
        raise ValueError("--candle-count must be between 1 and 200")
    if args.history_years <= 0 or args.history_years > 10:
        raise ValueError("--history-years must be between 1 and 10")
    if args.macro_lookback_days <= 0:
        raise ValueError("--macro-lookback-days must be positive")
    if args.disclosure_lookback_days <= 0:
        raise ValueError("--disclosure-lookback-days must be positive")
    if args.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")
    if args.max_retries < 0:
        raise ValueError("--max-retries cannot be negative")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(argv)
        _validate_args(args)
        payload = _execute(args)
        status_path = _write_status(args.output, payload)
        payload["status_path"] = str(status_path.resolve())
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except PipelineStageError as exc:
        if args is None:
            raise
        allowlist = exc.stage == "market" and _is_ip_allowlist_error(exc.cause)
        public_ip = (
            None
            if not allowlist or args.no_public_ip_lookup
            else _public_ip(min(args.timeout_seconds, 4.0))
        )
        payload: dict[str, object] = {
            "status": "blocked" if allowlist else "failed",
            "stage": exc.stage,
            "reason": "tossinvest_ip_allowlist" if allowlist else "pipeline_error",
            "error": str(exc.cause),
            "public_ip": public_ip,
            "next_action": (
                "Run .\\scripts\\run_live_pipeline.cmd so the supported Windows "
                "orchestrator can collect fresh adjusted Kiwoom read-only market "
                "evidence and retry in explicit Kiwoom-primary mode. Alternatively, "
                "register public_ip in the TossInvest allowlist and rerun the direct "
                "TossInvest command."
                if allowlist
                else "Review the stage error and rerun the same command after correction."
            ),
            "rerun_command": (
                ".\\scripts\\run_live_pipeline.cmd"
                if allowlist
                else "python -m alpha_cycle.live_pipeline_cli"
            ),
            "direct_rerun_command": "python -m alpha_cycle.live_pipeline_cli",
            "fallback_mode": (
                "orchestrated_kiwoom_primary_readonly" if allowlist else None
            ),
            "order_api_enabled": False,
        }
        status_path = _write_status(args.output, payload)
        payload["status_path"] = str(status_path.resolve())
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 3 if allowlist else 2
    except (ValueError, OSError, TypeError) as exc:
        output = args.output if args is not None else DEFAULT_OUTPUT_ROOT
        payload = {
            "status": "failed",
            "stage": "validation",
            "reason": "invalid_configuration",
            "error": str(exc),
            "order_api_enabled": False,
        }
        _write_status(output, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())