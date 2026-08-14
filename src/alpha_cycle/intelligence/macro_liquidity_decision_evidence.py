"""Integrate official U.S. macro/liquidity evidence with existing Korea context.

The evidence is a transmission map, not a universal macro score. It keeps real
rates, broad dollar, financial conditions, Fed balance sheet, reserve balances,
Korean policy rate/FX, investor flow, and semiconductor risk appetite separate.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

DEFAULT_MACRO_LIQUIDITY_POINTER = Path(
    "data/private/live-research/macro-liquidity-evidence/latest_macro_liquidity_evidence.json"
)
_REQUIRED_FALSE_FLAGS = (
    "historical_vintage_certified",
    "point_in_time_backtest_eligible",
    "decision_score_enabled",
    "composite_liquidity_score_enabled",
    "forecast_enabled",
    "causal_claim_enabled",
    "account_api_enabled",
    "holdings_api_enabled",
    "balance_api_enabled",
    "order_api_enabled",
)


@dataclass(frozen=True)
class MacroLiquidityDecisionEvidence:
    evidence_id: str
    evaluation_date: date
    series: pd.DataFrame
    coverage: pd.DataFrame
    decision_score_enabled: bool = False
    composite_liquidity_score_enabled: bool = False
    forecast_enabled: bool = False
    causal_claim_enabled: bool = False
    point_in_time_backtest_eligible: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.evidence_id
        ):
            raise ValueError("Macro liquidity decision evidence_id must be SHA-256")
        if self.series.empty or self.coverage.empty:
            raise ValueError("Macro liquidity decision evidence cannot be empty")
        if (
            self.decision_score_enabled
            or self.composite_liquidity_score_enabled
            or self.forecast_enabled
            or self.causal_claim_enabled
            or self.point_in_time_backtest_eligible
        ):
            raise ValueError("Macro liquidity decision evidence must remain non-scoring")


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], payload)


def _require_false(payload: Mapping[str, object], flags: tuple[str, ...]) -> None:
    for key in flags:
        if payload.get(key) is not False:
            raise ValueError(f"Macro liquidity evidence requires {key}=false")


def _finite_number(value: object, field: str) -> float:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted):
        raise ValueError(f"Macro liquidity {field} must be numeric")
    result = float(cast(float, converted))
    if not math.isfinite(result):
        raise ValueError(f"Macro liquidity {field} must be finite")
    return result


def _load_pointer(
    pointer_path: Path,
    evaluation_date: date,
) -> tuple[str, pd.DataFrame]:
    pointer = _json_object(pointer_path, "Macro liquidity pointer")
    if str(pointer.get("status", "")) != "macro_liquidity_evidence_captured":
        raise ValueError("Macro liquidity pointer status is invalid")
    _require_false(pointer, _REQUIRED_FALSE_FLAGS)
    if pointer.get("current_endpoint_snapshot") is not True:
        raise ValueError("Macro liquidity evidence must identify current_endpoint_snapshot=true")
    pointer_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if pointer_date != evaluation_date:
        raise ValueError(
            "Macro liquidity evaluation date mismatch: "
            f"evidence={pointer_date.isoformat()} decision={evaluation_date.isoformat()}"
        )
    evidence_id = str(pointer.get("evidence_id", "")).strip()
    if len(evidence_id) != 64 or any(
        char not in "0123456789abcdef" for char in evidence_id
    ):
        raise ValueError("Macro liquidity pointer evidence_id is invalid")
    manifest_path = Path(str(pointer.get("manifest_path", "")).strip())
    summary_path = Path(str(pointer.get("series_summary_path", "")).strip())
    manifest = _json_object(manifest_path, "Macro liquidity manifest")
    if str(manifest.get("evidence_id", "")) != evidence_id:
        raise ValueError("Macro liquidity pointer/manifest evidence mismatch")
    _require_false(manifest, _REQUIRED_FALSE_FLAGS)
    if manifest.get("current_endpoint_snapshot") is not True:
        raise ValueError("Macro liquidity manifest current-endpoint flag is missing")
    series = pd.read_csv(summary_path, dtype={"series_id": "string", "source_id": "string"})
    required = {
        "series_id",
        "dimension",
        "latest_date",
        "latest_value",
        "unit",
        "change_4_observations",
        "change_20_observations",
        "level_state",
        "interpretation",
    }
    missing = required - set(series.columns)
    if missing:
        raise ValueError(f"Macro liquidity summary missing columns: {sorted(missing)}")
    if series["series_id"].duplicated().any():
        raise ValueError("Macro liquidity summary contains duplicate series")
    expected = {"DFII10", "DTWEXBGS", "NFCI", "WALCL", "WRESBAL"}
    actual = set(series["series_id"].astype(str))
    if actual != expected:
        raise ValueError(
            "Macro liquidity series set mismatch: "
            f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    return evidence_id, series.sort_values("series_id", kind="stable").reset_index(drop=True)


def _macro_state(macro_regime: pd.DataFrame, series_id: str) -> Mapping[str, object] | None:
    if macro_regime.empty or "series_id" not in macro_regime.columns:
        return None
    rows = macro_regime.loc[macro_regime["series_id"].astype(str).eq(series_id)]
    if len(rows) != 1:
        return None
    return cast(Mapping[str, object], rows.iloc[0].to_dict())


def _flow_status(scorecards: pd.DataFrame) -> tuple[str, str]:
    if scorecards.empty:
        return "missing", "투자자 수급 scorecard가 없습니다."
    verified = (
        scorecards["investor_flow_evidence_verified"].fillna(False).astype(bool)
        if "investor_flow_evidence_verified" in scorecards.columns
        else pd.Series(False, index=scorecards.index, dtype="bool")
    )
    available = (
        scorecards["investor_flow_available"].fillna(False).astype(bool)
        if "investor_flow_available" in scorecards.columns
        else pd.Series(False, index=scorecards.index, dtype="bool")
    )
    if bool(verified.all()) and len(verified) > 0:
        return "available", "same-session investor-flow evidence가 모든 대상에서 검증됐습니다."
    if bool(available.any()):
        return (
            "partial",
            "investor-flow evidence는 있으나 same-session 검증이 아니므로 현재 자금흐름으로 점수화하지 않습니다.",
        )
    return "missing", "검증 가능한 한국 투자자 수급 evidence가 없습니다."


def _coverage_row(
    dimension: str,
    status: str,
    summary: str,
    source_scope: str,
) -> dict[str, object]:
    return {
        "dimension": dimension,
        "status": status,
        "summary": summary,
        "source_scope": source_scope,
        "decision_score_enabled": False,
    }


def build_macro_liquidity_decision_evidence(
    pointer_path: str | Path,
    macro_regime: pd.DataFrame,
    scorecards: pd.DataFrame,
    *,
    evaluation_date: date,
) -> MacroLiquidityDecisionEvidence:
    evidence_id, series = _load_pointer(Path(pointer_path), evaluation_date)
    lookup = series.set_index("series_id").to_dict(orient="index")
    dfii10 = cast(Mapping[str, object], lookup["DFII10"])
    dollar = cast(Mapping[str, object], lookup["DTWEXBGS"])
    nfci = cast(Mapping[str, object], lookup["NFCI"])
    walcl = cast(Mapping[str, object], lookup["WALCL"])
    reserves = cast(Mapping[str, object], lookup["WRESBAL"])

    rows = [
        _coverage_row(
            "us_real_discount_rate",
            "available",
            f"DFII10 {_finite_number(dfii10['latest_value'], 'DFII10 latest'):.2f}% / "
            f"20관측 변화 {_finite_number(dfii10['change_20_observations'], 'DFII10 change'):+.2f}%p.",
            "FRED/Board_of_Governors_DFII10",
        ),
        _coverage_row(
            "broad_us_dollar",
            "available",
            f"DTWEXBGS {_finite_number(dollar['latest_value'], 'DTWEXBGS latest'):.2f} / "
            f"20관측 변화 {_finite_number(dollar['change_20_observations'], 'DTWEXBGS change'):+.2f}.",
            "FRED/Board_of_Governors_DTWEXBGS",
        ),
        _coverage_row(
            "us_financial_conditions",
            "available",
            f"NFCI {_finite_number(nfci['latest_value'], 'NFCI latest'):+.3f} / "
            f"공식 level state={str(nfci['level_state'])}.",
            "FRED/Chicago_Fed_NFCI",
        ),
        _coverage_row(
            "fed_balance_sheet",
            "partial",
            f"WALCL {_finite_number(walcl['latest_value'], 'WALCL latest'):,.0f} {str(walcl['unit'])} / "
            f"4관측 변화 {_finite_number(walcl['change_4_observations'], 'WALCL change'):+,.0f}; "
            "단독 순유동성 score로 사용하지 않습니다.",
            "FRED/Board_of_Governors_WALCL",
        ),
        _coverage_row(
            "fed_reserve_balances",
            "partial",
            f"WRESBAL {_finite_number(reserves['latest_value'], 'WRESBAL latest'):,.0f} {str(reserves['unit'])} / "
            f"4관측 변화 {_finite_number(reserves['change_4_observations'], 'WRESBAL change'):+,.0f}; "
            "balance-sheet leg와 별개로 유지합니다.",
            "FRED/Board_of_Governors_WRESBAL",
        ),
    ]

    kr_rate = _macro_state(macro_regime, "kr_base_rate")
    if kr_rate is None:
        rows.append(
            _coverage_row(
                "korea_policy_rate",
                "missing",
                "ECOS 한국 기준금리 evidence가 현재 snapshot에 없습니다.",
                "BOK_ECOS",
            )
        )
    else:
        rows.append(
            _coverage_row(
                "korea_policy_rate",
                "available",
                f"한국 기준금리 {_finite_number(kr_rate['latest_value'], 'KR base rate'):.2f} / "
                f"regime={str(kr_rate['regime'])}.",
                "BOK_ECOS",
            )
        )

    usd_krw = _macro_state(macro_regime, "usd_krw")
    if usd_krw is None:
        rows.append(
            _coverage_row(
                "usd_krw",
                "missing",
                "ECOS USD/KRW evidence가 현재 snapshot에 없습니다.",
                "BOK_ECOS",
            )
        )
    else:
        rows.append(
            _coverage_row(
                "usd_krw",
                "available",
                f"USD/KRW {_finite_number(usd_krw['latest_value'], 'USD/KRW'):.2f} / "
                f"regime={str(usd_krw['regime'])}.",
                "BOK_ECOS",
            )
        )

    flow_state, flow_summary = _flow_status(scorecards)
    rows.append(
        _coverage_row(
            "korea_investor_flow",
            flow_state,
            flow_summary,
            "Kiwoom_investor_flow",
        )
    )
    rows.append(
        _coverage_row(
            "semiconductor_risk_appetite",
            "missing",
            "SOX/AI semiconductor benchmark 및 글로벌 반도체 상대강도 evidence가 아직 source-bounded market leg로 연결되지 않았습니다.",
            "market_benchmark_not_connected",
        )
    )
    coverage = pd.DataFrame(rows)
    return MacroLiquidityDecisionEvidence(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        series=series,
        coverage=coverage,
    )


def append_macro_liquidity_report(
    report: str,
    evidence: MacroLiquidityDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## Macro / Liquidity Vertical v1 (비점수)",
        "",
        f"- evidence: `{evidence.evidence_id[:12]}` / evaluation `{evidence.evaluation_date.isoformat()}`",
        "- 실질금리·광의달러·금융여건·Fed 총자산·은행 준비금·한국 금리/환율·수급을 서로 다른 transmission leg로 유지합니다.",
        "- WALCL 또는 WRESBAL 하나를 임의의 '순유동성' 점수로 사용하지 않습니다.",
        "- current official endpoints이므로 historical vintage/PIT/forecast/causal claim은 비활성입니다.",
        "",
        "| 경로 | 상태 | 현재 evidence | source |",
        "|---|---|---|---|",
    ]
    for raw in evidence.coverage.to_dict(orient="records"):
        lines.append(
            f"| {raw['dimension']} | {raw['status']} | {raw['summary']} | {raw['source_scope']} |"
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_MACRO_LIQUIDITY_POINTER",
    "MacroLiquidityDecisionEvidence",
    "append_macro_liquidity_report",
    "build_macro_liquidity_decision_evidence",
]
