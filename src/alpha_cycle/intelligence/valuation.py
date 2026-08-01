"""Point-in-time valuation and multi-period financial-history intelligence."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yaml

from alpha_cycle.intelligence.decision_scoring import COMPONENT_WEIGHTS, DecisionPolicy
from alpha_cycle.providers.opendart import CorpCode, normalize_listed_stock_code
from alpha_cycle.providers.opendart_valuation import (
    FinancialPeriodPayload,
    OpenDartValuationClient,
)

VALUATION_SCHEMA_VERSION = 1
KOREA_TZ = ZoneInfo("Asia/Seoul")
PERIOD_LABELS = {
    "11013": "Q1",
    "11012": "Q2",
    "11014": "Q3",
    "11011": "FY",
}
PERIOD_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}


@dataclass(frozen=True)
class MetricSpec:
    name: str
    aliases: tuple[str, ...]
    statements: tuple[str, ...]
    kind: str


METRIC_SPECS = (
    MetricSpec(
        "revenue",
        ("ifrs-full_revenue", "dart_revenue", "매출액", "영업수익", "revenue"),
        ("IS", "CIS"),
        "flow",
    ),
    MetricSpec(
        "operating_income",
        (
            "dart_operatingincomeloss",
            "ifrs-full_profitlossfromoperatingactivities",
            "영업이익손실",
            "영업이익",
            "operatingincomeloss",
        ),
        ("IS", "CIS"),
        "flow",
    ),
    MetricSpec(
        "net_income",
        (
            "ifrs-full_profitloss",
            "dart_profitloss",
            "당기순이익손실",
            "당기순이익",
            "profitloss",
        ),
        ("IS", "CIS"),
        "flow",
    ),
    MetricSpec("equity", ("ifrs-full_equity", "자본총계", "equity"), ("BS",), "stock"),
    MetricSpec(
        "liabilities",
        ("ifrs-full_liabilities", "부채총계", "liabilities"),
        ("BS",),
        "stock",
    ),
    MetricSpec(
        "cash",
        ("ifrs-full_cashandcashequivalents", "현금및현금성자산", "cashandcashequivalents"),
        ("BS",),
        "stock",
    ),
    MetricSpec(
        "inventory",
        ("ifrs-full_inventories", "재고자산", "inventories"),
        ("BS",),
        "stock",
    ),
    MetricSpec(
        "operating_cash_flow",
        (
            "ifrs-full_cashflowsfromusedinoperatingactivities",
            "영업활동현금흐름",
            "영업활동으로인한현금흐름",
        ),
        ("CF",),
        "cashflow",
    ),
    MetricSpec(
        "capex",
        (
            "ifrs-full_purchaseofpropertyplantandequipmentclassifiedasinvestingactivities",
            "유형자산의취득",
            "유형자산취득",
        ),
        ("CF",),
        "cashflow",
    ),
)


@dataclass(frozen=True)
class CompanySecurityMapping:
    securities: Mapping[str, str]


@dataclass(frozen=True)
class ValuationEvidenceSnapshot:
    captured_at: datetime
    evaluation_date: date
    research_snapshot_id: str
    market_snapshot_id: str
    history_years: int
    shares: pd.DataFrame
    security_values: pd.DataFrame
    financial_history: pd.DataFrame
    valuation_metrics: pd.DataFrame
    raw_valuation: object
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        _validate_snapshot_id(self.research_snapshot_id, "research_snapshot_id")
        _validate_snapshot_id(self.market_snapshot_id, "market_snapshot_id")
        if self.history_years <= 0:
            raise ValueError("history_years must be positive")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": VALUATION_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "research_snapshot_id": self.research_snapshot_id,
            "market_snapshot_id": self.market_snapshot_id,
            "history_years": self.history_years,
            "shares": _records(self.shares),
            "security_values": _records(self.security_values),
            "financial_history": _records(self.financial_history),
            "valuation_metrics": _records(self.valuation_metrics),
            "raw_valuation": self.raw_valuation,
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
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ValueError("Valuation snapshot values must be finite")
        return value
    if isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Valuation snapshot value is not serializable: {type(value).__name__}")


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
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _read_json(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return cast(Mapping[str, object], payload)


def _snapshot_directory(path: str | Path) -> Path:
    directory = Path(path)
    if not directory.is_dir() or not (directory / "manifest.json").is_file():
        raise ValueError(f"Snapshot directory is invalid: {directory}")
    return directory


def _ticker(value: object) -> str:
    return normalize_listed_stock_code(value)


def _normalized(value: object) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value).strip().casefold())


def _amount(value: object) -> float | None:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    result = float(-number if negative else number)
    return result if math.isfinite(result) else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def _growth(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return current / abs(prior) - 1.0


def _as_rows(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw_rows = payload.get("list", [])
    if not isinstance(raw_rows, list):
        raise ValueError("OpenDART financial list must be an array")
    rows = [cast(Mapping[str, object], value) for value in raw_rows if isinstance(value, dict)]
    if len(rows) != len(raw_rows):
        raise ValueError("OpenDART financial rows must be objects")
    return rows


def _candidate_score(raw: Mapping[str, object], spec: MetricSpec) -> int:
    statement = str(raw.get("sj_div", "")).strip().upper()
    if statement not in spec.statements:
        return 0
    account_id = _normalized(raw.get("account_id", ""))
    account_name = _normalized(raw.get("account_nm", ""))
    score = 0
    for alias_value in spec.aliases:
        alias = _normalized(alias_value)
        if alias in {account_id, account_name}:
            score = max(score, 100)
        elif alias and (alias in account_id or alias in account_name):
            score = max(score, 60)
    if score == 0:
        return 0
    detail = str(raw.get("account_detail", "")).strip()
    if detail in {"", "-"}:
        score += 5
    order = str(raw.get("ord", "")).strip()
    if order.isdigit():
        score += max(0, 5 - min(int(order), 5))
    return score


def _select_metric(
    rows: Sequence[Mapping[str, object]],
    spec: MetricSpec,
) -> Mapping[str, object] | None:
    candidates = [(raw, _candidate_score(raw, spec)) for raw in rows]
    candidates = [(raw, score) for raw, score in candidates if score > 0]
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item[1],
            str(item[0].get("account_detail", "")) in {"", "-"},
            str(item[0].get("account_id", "")),
        ),
        reverse=True,
    )
    return candidates[0][0]


def _extract_period(period: FinancialPeriodPayload) -> dict[str, object]:
    rows = _as_rows(period.payload)
    label = PERIOD_LABELS[period.report_code]
    result: dict[str, object] = {
        "ticker": period.ticker,
        "business_year": period.business_year,
        "report_code": period.report_code,
        "period_label": label,
        "period_order": PERIOD_ORDER[label],
        "period_end": period.period_end,
        "available_date": period.available_date,
        "derived": False,
    }
    for spec in METRIC_SPECS:
        selected = _select_metric(rows, spec)
        current: float | None = None
        current_ytd: float | None = None
        prior_same: float | None = None
        prior_ytd: float | None = None
        account_id: str | None = None
        if selected is not None:
            account_id = str(selected.get("account_id", "")).strip()
            if spec.kind == "flow":
                current = _amount(selected.get("thstrm_amount"))
                current_ytd = (
                    current
                    if period.report_code == "11011"
                    else _amount(selected.get("thstrm_add_amount")) or current
                )
                prior_same = (
                    _amount(selected.get("frmtrm_amount"))
                    if period.report_code == "11011"
                    else _amount(selected.get("frmtrm_q_amount"))
                )
                prior_ytd = (
                    prior_same
                    if period.report_code == "11011"
                    else _amount(selected.get("frmtrm_add_amount")) or prior_same
                )
            elif spec.kind == "stock":
                current = _amount(selected.get("thstrm_amount"))
                prior_same = _amount(selected.get("frmtrm_amount"))
            else:
                current_ytd = _amount(selected.get("thstrm_amount"))
                prior_ytd = _amount(selected.get("frmtrm_amount"))
        result[spec.name] = current
        result[f"{spec.name}_ytd"] = current_ytd
        result[f"{spec.name}_prior_same"] = prior_same
        result[f"{spec.name}_prior_ytd"] = prior_ytd
        result[f"{spec.name}_account_id"] = account_id
    return result


def _derive_q4(history: pd.DataFrame) -> pd.DataFrame:
    derived: list[dict[str, object]] = []
    for (ticker, year), group in history.groupby(["ticker", "business_year"], sort=False):
        by_label = {str(row["period_label"]): row for _, row in group.iterrows()}
        if "FY" not in by_label or "Q3" not in by_label:
            continue
        fiscal = by_label["FY"]
        q3 = by_label["Q3"]
        record = fiscal.to_dict()
        record.update(
            {
                "ticker": ticker,
                "business_year": int(year),
                "report_code": "DERIVED_Q4",
                "period_label": "Q4",
                "period_order": PERIOD_ORDER["Q4"],
                "derived": True,
                "available_date": fiscal["available_date"],
            }
        )
        for metric in ("revenue", "operating_income", "net_income"):
            annual = _number(fiscal.get(metric))
            q3_ytd = _number(q3.get(f"{metric}_ytd"))
            annual_prior = _number(fiscal.get(f"{metric}_prior_same"))
            q3_prior_ytd = _number(q3.get(f"{metric}_prior_ytd"))
            record[metric] = (
                annual - q3_ytd if annual is not None and q3_ytd is not None else None
            )
            record[f"{metric}_prior_same"] = (
                annual_prior - q3_prior_ytd
                if annual_prior is not None and q3_prior_ytd is not None
                else None
            )
            record[f"{metric}_ytd"] = annual
            record[f"{metric}_prior_ytd"] = annual_prior
        for metric in ("operating_cash_flow", "capex"):
            annual_ytd = _number(fiscal.get(f"{metric}_ytd"))
            q3_ytd = _number(q3.get(f"{metric}_ytd"))
            record[f"{metric}_ytd"] = (
                annual_ytd - q3_ytd
                if annual_ytd is not None and q3_ytd is not None
                else None
            )
        derived.append(record)
    if not derived:
        return history
    return pd.concat([history, pd.DataFrame(derived)], ignore_index=True, sort=False)


def _number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def build_financial_history(
    periods: Sequence[FinancialPeriodPayload],
) -> pd.DataFrame:
    if not periods:
        raise ValueError("At least one OpenDART financial period is required")
    history = pd.DataFrame([_extract_period(period) for period in periods])
    history = _derive_q4(history)
    for metric in ("revenue", "operating_income", "net_income"):
        history[f"{metric}_yoy"] = [
            _growth(_number(current), _number(prior))
            for current, prior in zip(
                history[metric],
                history[f"{metric}_prior_same"],
                strict=True,
            )
        ]
    history["operating_margin"] = [
        _ratio(_number(op), _number(revenue))
        for op, revenue in zip(
            history["operating_income"], history["revenue"], strict=True
        )
    ]
    history["operating_margin_prior"] = [
        _ratio(_number(op), _number(revenue))
        for op, revenue in zip(
            history["operating_income_prior_same"],
            history["revenue_prior_same"],
            strict=True,
        )
    ]
    history["operating_margin_change_yoy_pp"] = [
        (current - prior) * 100.0
        if current is not None and prior is not None
        else None
        for current, prior in zip(
            history["operating_margin"],
            history["operating_margin_prior"],
            strict=True,
        )
    ]
    history["free_cash_flow_ytd"] = [
        ocf - abs(capex) if ocf is not None and capex is not None else None
        for ocf, capex in zip(
            history["operating_cash_flow_ytd"], history["capex_ytd"], strict=True
        )
    ]
    history = history.sort_values(
        ["ticker", "period_end", "period_order"], kind="stable"
    ).reset_index(drop=True)
    for metric in ("revenue_yoy", "operating_income_yoy", "net_income_yoy"):
        acceleration = pd.Series(np.nan, index=history.index, dtype="float64")
        quarter_mask = history["period_label"].isin(["Q1", "Q2", "Q3", "Q4"])
        for _, group in history.loc[quarter_mask].groupby("ticker", sort=False):
            values = pd.to_numeric(group[metric], errors="coerce")
            acceleration.loc[group.index] = values.diff()
        history[f"{metric}_acceleration"] = acceleration
    return history


def load_security_mappings(
    path: str | Path | None,
) -> dict[str, CompanySecurityMapping]:
    if path is None:
        return {}
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("companies"), dict):
        raise ValueError("Security mapping config must contain a companies object")
    companies = cast(Mapping[object, object], payload["companies"])
    result: dict[str, CompanySecurityMapping] = {}
    for raw_ticker, raw_company in companies.items():
        ticker = _ticker(raw_ticker)
        if not isinstance(raw_company, dict):
            raise ValueError(f"Security mapping entry must be an object: {ticker}")
        securities = raw_company.get("securities")
        if not isinstance(securities, dict):
            raise ValueError(f"Security mapping requires securities: {ticker}")
        mapping: dict[str, str] = {}
        for raw_name, raw_symbol in cast(Mapping[object, object], securities).items():
            name = str(raw_name).strip()
            if not name:
                raise ValueError(f"Security name cannot be blank: {ticker}")
            mapping[name] = _ticker(raw_symbol)
        result[ticker] = CompanySecurityMapping(mapping)
    return result


def _corp_records(raw_opendart: Mapping[str, object]) -> dict[str, CorpCode]:
    result: dict[str, CorpCode] = {}
    for raw_ticker, raw_company in raw_opendart.items():
        if str(raw_ticker).startswith("_"):
            continue
        if not isinstance(raw_company, dict) or not isinstance(raw_company.get("corp"), dict):
            raise ValueError(f"Research raw OpenDART corp metadata is missing: {raw_ticker}")
        corp = cast(Mapping[str, object], raw_company["corp"])
        ticker = _ticker(corp.get("stock_code", raw_ticker))
        result[ticker] = CorpCode(
            corp_code=str(corp.get("corp_code", "")).strip(),
            corp_name=str(corp.get("corp_name", "")).strip(),
            stock_code=ticker,
            modify_date=date.fromisoformat(str(corp.get("modify_date", ""))),
        )
    if not result:
        raise ValueError("Research snapshot contains no company metadata")
    return result


def _load_prices(market_dir: Path) -> pd.DataFrame:
    prices = pd.read_csv(
        market_dir / "prices.csv",
        dtype={"symbol": "string"},
    )
    required = {"symbol", "timestamp", "last_price", "currency"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"Market prices are missing columns: {sorted(missing)}")
    prices["symbol"] = prices["symbol"].map(_ticker)
    prices["timestamp"] = pd.to_datetime(prices["timestamp"], utc=True, errors="raise")
    prices["last_price"] = pd.to_numeric(prices["last_price"], errors="raise")
    if prices["symbol"].duplicated().any():
        raise ValueError("Market prices contain duplicate symbols")
    if (prices["last_price"] <= 0).any():
        raise ValueError("Market prices must be positive")
    return prices.sort_values("symbol", kind="stable").reset_index(drop=True)


def _security_values(
    shares: pd.DataFrame,
    prices: pd.DataFrame,
    mappings: Mapping[str, CompanySecurityMapping],
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    price_lookup = prices.set_index("symbol")["last_price"].to_dict()
    timestamp_lookup = prices.set_index("symbol")["timestamp"].to_dict()
    rows: list[dict[str, object]] = []
    warnings: list[str] = []
    for ticker, group in shares.groupby("ticker", sort=False):
        company_mapping = mappings.get(str(ticker))
        class_rows = group.loc[
            group["security_class"].isin(["common", "preferred", "other"])
            & (pd.to_numeric(group["issued_shares"], errors="coerce").fillna(0) > 0)
        ].copy()
        common_rows = class_rows.loc[class_rows["security_class"] == "common"]
        if len(common_rows) > 1 and company_mapping is None:
            raise ValueError(f"Multiple common-share rows require explicit mapping: {ticker}")
        total_rows = group.loc[group["security_class"] == "total"]
        class_total = int(pd.to_numeric(class_rows["issued_shares"], errors="coerce").sum())
        if len(total_rows) == 1:
            reported_total = _number(total_rows.iloc[0].get("issued_shares"))
            if reported_total is not None and int(reported_total) != class_total:
                warnings.append(
                    f"{ticker}: security-class issued shares do not equal the reported total"
                )
        for _, raw in class_rows.iterrows():
            security_name = str(raw["security_name"])
            symbol: str | None = None
            mapping_source = "unmapped"
            if company_mapping is not None and security_name in company_mapping.securities:
                symbol = company_mapping.securities[security_name]
                mapping_source = "explicit"
            elif raw["security_class"] == "common" and len(common_rows) == 1:
                symbol = str(ticker)
                mapping_source = "default_common"
            price = _number(price_lookup.get(symbol)) if symbol is not None else None
            issued = _number(raw.get("issued_shares"))
            rows.append(
                {
                    **raw.to_dict(),
                    "symbol": symbol,
                    "mapping_source": mapping_source,
                    "price": price,
                    "price_timestamp": timestamp_lookup.get(symbol) if symbol is not None else None,
                    "security_market_value": (
                        price * issued if price is not None and issued is not None else None
                    ),
                    "priced": price is not None,
                }
            )
    return (
        pd.DataFrame(rows).sort_values(
            ["ticker", "security_class", "security_name"], kind="stable"
        ).reset_index(drop=True),
        tuple(warnings),
    )


def _latest_annual(history: pd.DataFrame, ticker: str) -> Mapping[str, object] | None:
    annual = history.loc[
        (history["ticker"] == ticker) & (history["period_label"] == "FY")
    ].sort_values("period_end", kind="stable")
    if annual.empty:
        return None
    return cast(Mapping[str, object], annual.iloc[-1].to_dict())


def _valuation_metrics(
    securities: pd.DataFrame,
    history: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker, group in securities.groupby("ticker", sort=False):
        required = group.loc[pd.to_numeric(group["issued_shares"], errors="coerce") > 0]
        priced = required.loc[required["priced"].astype(bool)]
        complete = len(required) > 0 and len(priced) == len(required)
        proxy = float(pd.to_numeric(priced["security_market_value"], errors="coerce").sum())
        market_cap = proxy if complete else None
        missing = sorted(required.loc[~required["priced"].astype(bool), "security_name"].astype(str))
        annual = _latest_annual(history, str(ticker))
        revenue = _number(annual.get("revenue")) if annual else None
        net_income = _number(annual.get("net_income")) if annual else None
        equity = _number(annual.get("equity")) if annual else None
        fcf = _number(annual.get("free_cash_flow_ytd")) if annual else None
        pe = _ratio(market_cap, net_income) if net_income is not None and net_income > 0 else None
        pb = _ratio(market_cap, equity) if equity is not None and equity > 0 else None
        ps = _ratio(market_cap, revenue) if revenue is not None and revenue > 0 else None
        fcf_yield = _ratio(fcf, market_cap) if market_cap is not None else None
        earnings_yield = _ratio(net_income, market_cap) if market_cap is not None else None
        rows.append(
            {
                "ticker": str(ticker),
                "share_period_end": group["period_end"].max(),
                "share_available_date": group["available_date"].max(),
                "priced_security_classes": len(priced),
                "required_security_classes": len(required),
                "market_cap_complete": complete,
                "missing_security_names": json.dumps(missing, ensure_ascii=False),
                "market_cap_proxy": proxy if len(priced) else None,
                "market_cap": market_cap,
                "annual_reference_year": (
                    int(annual["business_year"]) if annual is not None else None
                ),
                "annual_revenue": revenue,
                "annual_net_income": net_income,
                "annual_equity": equity,
                "annual_free_cash_flow": fcf,
                "pe": pe,
                "pb": pb,
                "ps": ps,
                "fcf_yield": fcf_yield,
                "earnings_yield": earnings_yield,
                "valuation_score": None,
                "valuation_status": (
                    "complete_unscored"
                    if complete and annual is not None
                    else "partial_market_cap"
                    if not complete
                    else "no_annual_financial_reference"
                ),
            }
        )
    result = pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)
    eligible = result.loc[
        result["market_cap_complete"].astype(bool)
        & result[["pe", "pb", "ps", "fcf_yield"]].notna().any(axis=1)
    ].copy()
    if len(eligible) >= 2:
        ranks = pd.DataFrame(index=eligible.index)
        for metric in ("pe", "pb", "ps"):
            ranks[metric] = pd.to_numeric(eligible[metric], errors="coerce").rank(
                ascending=False, pct=True
            )
        ranks["fcf_yield"] = pd.to_numeric(
            eligible["fcf_yield"], errors="coerce"
        ).rank(ascending=True, pct=True)
        percentile = ranks.mean(axis=1, skipna=True)
        raw_score = 1.0 + 4.0 * percentile
        shrinkage = len(eligible) / (len(eligible) + 3.0)
        scores = 3.0 + (raw_score - 3.0) * shrinkage
        result.loc[eligible.index, "valuation_score"] = scores
        result.loc[eligible.index, "valuation_status"] = "complete_peer_relative_scored"
    return result


def _raw_company_payload(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        return {}
    return cast(Mapping[str, object], value)


def build_valuation_evidence_snapshot(
    research_snapshot: str | Path,
    market_snapshot: str | Path,
    client: OpenDartValuationClient,
    *,
    history_years: int = 3,
    fs_div: str = "CFS",
    security_mappings: Mapping[str, CompanySecurityMapping] | None = None,
    now: datetime | None = None,
) -> ValuationEvidenceSnapshot:
    research_dir = _snapshot_directory(research_snapshot)
    market_dir = _snapshot_directory(market_snapshot)
    research_manifest = _read_json(research_dir / "manifest.json")
    market_manifest = _read_json(market_dir / "manifest.json")
    research_id = str(research_manifest.get("snapshot_id", ""))
    market_id = str(market_manifest.get("snapshot_id", ""))
    _validate_snapshot_id(research_id, "research_snapshot_id")
    _validate_snapshot_id(market_id, "market_snapshot_id")
    linked_market = str(research_manifest.get("market_snapshot_id", "")).strip()
    if linked_market and linked_market != market_id:
        raise ValueError("Research snapshot is linked to a different market snapshot")
    evaluation_date = date.fromisoformat(str(research_manifest.get("evaluation_date", "")))
    market_captured = datetime.fromisoformat(str(market_manifest.get("captured_at", "")))
    if market_captured.tzinfo is None or market_captured.utcoffset() is None:
        raise ValueError("Market manifest captured_at must be timezone-aware")
    if market_captured.astimezone(KOREA_TZ).date() > evaluation_date:
        raise ValueError("Market snapshot contains prices after the evaluation date")

    raw_opendart = _read_json(research_dir / "raw_opendart.json")
    corps = _corp_records(raw_opendart)
    prices = _load_prices(market_dir)
    share_frames: list[pd.DataFrame] = []
    periods: list[FinancialPeriodPayload] = []
    raw: dict[str, object] = {}
    warnings: list[str] = []
    for ticker in sorted(corps):
        corp = corps[ticker]
        stock = client.latest_stock_totals(corp, evaluation_date=evaluation_date)
        company_periods = client.financial_history_payloads(
            corp,
            evaluation_date=evaluation_date,
            history_years=history_years,
            fs_div=fs_div,
        )
        share_frames.append(stock.frame)
        periods.extend(company_periods)
        raw[ticker] = {
            "corp": {
                "corp_code": corp.corp_code,
                "corp_name": corp.corp_name,
                "stock_code": corp.stock_code,
                "modify_date": corp.modify_date.isoformat(),
            },
            "stock_totals": stock.raw_payload,
            "financial_periods": [
                {
                    "business_year": period.business_year,
                    "report_code": period.report_code,
                    "period_end": period.period_end.isoformat(),
                    "available_date": period.available_date.isoformat(),
                    "payload": dict(period.payload),
                }
                for period in company_periods
            ],
            "source_research_company": dict(
                _raw_company_payload(raw_opendart.get(ticker))
            ),
        }
    shares = pd.concat(share_frames, ignore_index=True)
    financial_history = build_financial_history(periods)
    security_values, security_warnings = _security_values(
        shares,
        prices,
        dict(security_mappings or {}),
    )
    warnings.extend(security_warnings)
    valuation_metrics = _valuation_metrics(security_values, financial_history)
    if not valuation_metrics["market_cap_complete"].astype(bool).all():
        warnings.append(
            "Some company market capitalizations are partial because one or more equity "
            "classes lack an explicit symbol mapping or price."
        )
    warnings.append(
        "Valuation scores are peer-relative percentile ranks shrunk toward neutral; they are "
        "not absolute fair-value estimates or target prices."
    )
    return ValuationEvidenceSnapshot(
        captured_at=now or datetime.now(UTC),
        evaluation_date=evaluation_date,
        research_snapshot_id=research_id,
        market_snapshot_id=market_id,
        history_years=history_years,
        shares=shares,
        security_values=security_values,
        financial_history=financial_history,
        valuation_metrics=valuation_metrics,
        raw_valuation=raw,
        warnings=tuple(warnings),
    )


def write_valuation_evidence_snapshot(
    output_root: str | Path,
    snapshot: ValuationEvidenceSnapshot,
) -> tuple[Path, ...]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    names = (
        "manifest.json",
        "shares.csv",
        "security_values.csv",
        "financial_history.csv",
        "valuation_metrics.csv",
        "raw_valuation.json",
    )
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if manifest.get("snapshot_id") != snapshot.snapshot_id:
            raise ValueError("Existing valuation snapshot conflicts with requested snapshot")
        return tuple(directory / name for name in names)
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        frames = {
            "shares.csv": snapshot.shares,
            "security_values.csv": snapshot.security_values,
            "financial_history.csv": snapshot.financial_history,
            "valuation_metrics.csv": snapshot.valuation_metrics,
        }
        for name, frame in frames.items():
            frame.to_csv(temporary / name, index=False)
        (temporary / "raw_valuation.json").write_text(
            json.dumps(snapshot.raw_valuation, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": VALUATION_SCHEMA_VERSION,
            "snapshot_id": snapshot.snapshot_id,
            "captured_at": snapshot.captured_at.isoformat(),
            "evaluation_date": snapshot.evaluation_date.isoformat(),
            "research_snapshot_id": snapshot.research_snapshot_id,
            "market_snapshot_id": snapshot.market_snapshot_id,
            "history_years": snapshot.history_years,
            "symbols": snapshot.valuation_metrics["ticker"].astype(str).tolist(),
            "market_cap_complete_count": int(
                snapshot.valuation_metrics["market_cap_complete"].astype(bool).sum()
            ),
            "valuation_scored_count": int(
                snapshot.valuation_metrics["valuation_score"].notna().sum()
            ),
            "warnings": list(snapshot.warnings),
            "valuation_method": "peer_relative_percentile_shrunk_to_neutral",
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


def apply_valuation_to_scorecards(
    scorecards: pd.DataFrame,
    valuation_metrics: pd.DataFrame,
    policy: DecisionPolicy,
) -> pd.DataFrame:
    if valuation_metrics.empty:
        return scorecards.copy()
    metrics = valuation_metrics.copy()
    metrics["ticker"] = metrics["ticker"].map(_ticker)
    if metrics["ticker"].duplicated().any():
        raise ValueError("Valuation metrics contain duplicate tickers")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].map(_ticker)
    lookup = metrics.set_index("ticker").to_dict(orient="index")
    rows: list[dict[str, object]] = []
    for raw in result.to_dict(orient="records"):
        row = dict(raw)
        ticker = str(row["ticker"])
        valuation = cast(Mapping[str, object], lookup.get(ticker, {}))
        valuation_score = _number(valuation.get("valuation_score"))
        row["valuation_score"] = valuation_score
        row["valuation_status"] = str(
            valuation.get("valuation_status", "not_available")
        )
        weighted = 0.0
        available = 0.0
        for component, weight in COMPONENT_WEIGHTS.items():
            score = _number(row.get(component))
            if score is not None:
                weighted += score * weight
                available += weight
        composite = weighted / available if available else None
        coverage = available / sum(COMPONENT_WEIGHTS.values())
        row["composite_score"] = composite
        row["score_coverage"] = coverage
        market_score = _number(row.get("market_timing_score"))
        if composite is None or coverage < policy.minimum_coverage:
            state, action = "insufficient_data", "research_gap"
        elif composite >= policy.positive_threshold:
            state = "positive_setup"
            action = (
                "fundamental_positive_timing_confirmed"
                if market_score is not None and market_score >= 3.2
                else "fundamental_positive_wait_for_timing"
            )
        elif composite >= policy.mixed_threshold:
            state, action = "mixed_setup", "selective_or_wait"
        else:
            state, action = "negative_setup", "avoid_or_reduce_candidate"
        row["decision_state"] = state
        row["action_bias"] = action
        opposing = _decode_json_list(row.get("opposing_evidence"))
        opposing = [
            item for item in opposing if item != "밸류에이션·컨센서스 데이터 미연결"
        ]
        if valuation_score is None:
            opposing.append(f"밸류에이션 상태: {row['valuation_status']}")
        row["opposing_evidence"] = json.dumps(opposing, ensure_ascii=False)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)


def _decode_json_list(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    parsed: object = json.loads(value)
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def append_valuation_report(
    report: str,
    valuation_metrics: pd.DataFrame,
    financial_history: pd.DataFrame,
) -> str:
    lines = [report.rstrip(), "", "## 밸류에이션 및 다기간 실적", ""]
    metrics = valuation_metrics.set_index("ticker")
    for ticker in metrics.index.astype(str):
        row = cast(Mapping[str, object], metrics.loc[ticker].to_dict())
        history = financial_history.loc[
            (financial_history["ticker"].astype(str) == ticker)
            & financial_history["period_label"].isin(["Q1", "Q2", "Q3", "Q4"])
        ].sort_values("period_end", kind="stable")
        lines.extend(
            [
                f"### {ticker}",
                "",
                f"- 밸류에이션 상태: {row.get('valuation_status')}",
                f"- 완전 시가총액: {_fmt_number(row.get('market_cap'))}",
                f"- 부분 시가총액 프록시: {_fmt_number(row.get('market_cap_proxy'))}",
                f"- PER: {_fmt_multiple(row.get('pe'))}",
                f"- PBR: {_fmt_multiple(row.get('pb'))}",
                f"- PSR: {_fmt_multiple(row.get('ps'))}",
                f"- FCF 수익률: {_fmt_percent(row.get('fcf_yield'))}",
                f"- 밸류에이션 점수: {_fmt_score(row.get('valuation_score'))}",
                "- 점수는 이 스냅샷 내 완전한 기업끼리의 상대순위를 중립값으로 축소한 값",
            ]
        )
        if not history.empty:
            latest = cast(Mapping[str, object], history.iloc[-1].to_dict())
            lines.extend(
                [
                    f"- 최근 분기: {latest.get('business_year')} {latest.get('period_label')}",
                    f"- 매출 YoY: {_fmt_percent(latest.get('revenue_yoy'))}",
                    f"- 영업이익 YoY: {_fmt_percent(latest.get('operating_income_yoy'))}",
                    "- 영업이익 성장 가속도: "
                    f"{_fmt_percent(latest.get('operating_income_yoy_acceleration'))}",
                ]
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _fmt_number(value: object) -> str:
    number = _number(value)
    return f"{number:,.0f}" if number is not None else "N/A"


def _fmt_multiple(value: object) -> str:
    number = _number(value)
    return f"{number:.2f}x" if number is not None else "N/A"


def _fmt_percent(value: object) -> str:
    number = _number(value)
    return f"{number:.1%}" if number is not None else "N/A"


def _fmt_score(value: object) -> str:
    number = _number(value)
    return f"{number:.2f}/5" if number is not None else "미평가"


__all__ = [
    "CompanySecurityMapping",
    "ValuationEvidenceSnapshot",
    "append_valuation_report",
    "apply_valuation_to_scorecards",
    "build_financial_history",
    "build_valuation_evidence_snapshot",
    "load_security_mappings",
    "write_valuation_evidence_snapshot",
]
