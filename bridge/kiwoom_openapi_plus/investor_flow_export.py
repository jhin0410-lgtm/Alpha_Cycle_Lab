"""Read-only Kiwoom OpenAPI+ OPT10059 investor-flow probe.

The probe deliberately stays outside the decision score. It requests net-buy quantity
in single-share units, preserves the provider's Korean field names as raw evidence,
and writes an immutable local snapshot for live semantic verification.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from market_export import (
    DEFAULT_SYMBOLS,
    PROVIDER,
    KiwoomMarketExporter,
    _clean,
    _validate_symbols,
)
from market_export_bootstrap import _flush_and_hard_exit

TR_CODE = "opt10059"
SOURCE_SCOPE = "kiwoom_openapi_plus_opt10059_net_buy_quantity"
SEMANTIC_STATUS = "provider_field_mapping_pending_live_certification"
DEFAULT_OUTPUT_ROOT = Path(
    "data/private/live-research/kiwoom-openapi-plus-investor-flow"
)
_KST = datetime.now().astimezone().tzinfo
_DATE = re.compile(r"^[0-9]{8}$")

_PROVIDER_FIELDS = {
    "date": "일자",
    "current_price": "현재가",
    "change_sign": "대비기호",
    "change": "전일대비",
    "change_percent": "등락율",
    "cumulative_volume": "누적거래량",
    "cumulative_value": "누적거래대금",
    "individual": "개인투자자",
    "foreign": "외국인투자자",
    "institution": "기관계",
    "financial_investment": "금융투자",
    "insurance": "보험",
    "investment_trust": "투신",
    "other_finance": "기타금융",
    "bank": "은행",
    "pension": "연기금등",
    "private_fund": "사모펀드",
    "state": "국가",
    "other_corporation": "기타법인",
    "domestic_foreign": "내외국인",
}
_INVESTOR_KEYS = (
    "individual",
    "foreign",
    "institution",
    "financial_investment",
    "insurance",
    "investment_trust",
    "other_finance",
    "bank",
    "pension",
    "private_fund",
    "state",
    "other_corporation",
    "domestic_foreign",
)


def _integer(raw: object) -> int | None:
    text = _clean(raw).replace(",", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def _decimal(raw: object) -> float | None:
    text = _clean(raw).replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class InvestorFlowRecord:
    ticker: str
    date: str
    current_price: int | None
    change: int | None
    change_percent: float | None
    cumulative_volume: int | None
    cumulative_value: int | None
    individual_net_buy_shares: int | None
    foreign_net_buy_shares: int | None
    institution_net_buy_shares: int | None
    financial_investment_net_buy_shares: int | None
    insurance_net_buy_shares: int | None
    investment_trust_net_buy_shares: int | None
    other_finance_net_buy_shares: int | None
    bank_net_buy_shares: int | None
    pension_net_buy_shares: int | None
    private_fund_net_buy_shares: int | None
    state_net_buy_shares: int | None
    other_corporation_net_buy_shares: int | None
    domestic_foreign_net_buy_shares: int | None
    raw_json: str
    request_name: str
    tr_code: str
    screen_no: str
    previous_next: str


@dataclass(frozen=True)
class InvestorFlowManifest:
    schema_version: str
    status: str
    provider: str
    source_scope: str
    semantic_status: str
    snapshot_id: str
    captured_at: str
    reference_date: str
    symbols: tuple[str, ...]
    record_count: int
    limit_per_symbol: int
    tr_code: str
    request_mode: str
    amount_quantity_type: str
    trade_type: str
    unit_type: str
    first_page_only: bool
    account_api_enabled: bool
    holdings_api_enabled: bool
    balance_api_enabled: bool
    order_api_enabled: bool
    decision_score_enabled: bool
    warnings: tuple[str, ...]
    provider_messages: tuple[str, ...]


class KiwoomInvestorFlowExporter(KiwoomMarketExporter):
    """Investor-flow-only extension of the existing hardened market session."""

    def _investor_payload(
        self,
        *,
        screen_no: str,
        request_name: str,
        tr_code: str,
        previous_next: str,
    ) -> dict[str, object]:
        repeat = int(
            self.control.dynamicCall(
                "GetRepeatCnt(QString, QString)",
                tr_code,
                request_name,
            )
        )
        rows: list[dict[str, str]] = []
        for index in range(max(repeat, 0)):
            rows.append(
                {
                    key: self._comm_data(tr_code, request_name, index, label)
                    for key, label in _PROVIDER_FIELDS.items()
                }
            )
        return {
            "kind": "investor_flow",
            "screen_no": screen_no,
            "request_name": request_name,
            "tr_code": tr_code,
            "previous_next": previous_next,
            "rows": rows,
        }

    def _on_receive_tr_data(
        self,
        screen_no: object,
        request_name: object,
        tr_code: object,
        record_name: object,
        previous_next: object,
        data_length: object,
        error_code: object,
        message: object,
        supplementary_message: object,
    ) -> None:
        received_request = _clean(request_name)
        if not received_request.startswith("investor_"):
            super()._on_receive_tr_data(
                screen_no,
                request_name,
                tr_code,
                record_name,
                previous_next,
                data_length,
                error_code,
                message,
                supplementary_message,
            )
            return
        if self._pending_request_name != received_request:
            return
        payload = self._investor_payload(
            screen_no=_clean(screen_no),
            request_name=received_request,
            tr_code=_clean(tr_code),
            previous_next=_clean(previous_next),
        )
        payload["error_code"] = _clean(error_code)
        payload["message"] = _clean(message)
        payload["supplementary_message"] = _clean(supplementary_message)
        self._pending_payload = payload
        if self._request_loop is not None:
            self._request_loop.quit()

    def investor_flows(
        self,
        ticker: str,
        *,
        screen_no: str,
        reference_date: str,
        limit: int,
    ) -> list[InvestorFlowRecord]:
        if not _DATE.fullmatch(reference_date):
            raise ValueError("reference_date must use YYYYMMDD")
        if limit <= 0 or limit > 120:
            raise ValueError("investor flow limit must be between 1 and 120")
        request_name = f"investor_{ticker}"
        payload = self._request(
            request_name=request_name,
            tr_code=TR_CODE,
            screen_no=screen_no,
            inputs=(
                ("일자", reference_date),
                ("종목코드", ticker),
                ("금액수량구분", "2"),
                ("매매구분", "0"),
                ("단위구분", "1"),
            ),
        )
        rows_object = payload.get("rows")
        if not isinstance(rows_object, list):
            raise RuntimeError(f"investor-flow payload missing rows for {ticker}")
        records: list[InvestorFlowRecord] = []
        for row_object in rows_object[:limit]:
            if not isinstance(row_object, dict):
                continue
            raw = {str(key): _clean(value) for key, value in row_object.items()}
            date = raw.get("date", "")
            if not _DATE.fullmatch(date):
                continue
            investor_values = {key: _integer(raw.get(key, "")) for key in _INVESTOR_KEYS}
            if all(value is None for value in investor_values.values()):
                continue
            records.append(
                InvestorFlowRecord(
                    ticker=ticker,
                    date=date,
                    current_price=_integer(raw.get("current_price", "")),
                    change=_integer(raw.get("change", "")),
                    change_percent=_decimal(raw.get("change_percent", "")),
                    cumulative_volume=_integer(raw.get("cumulative_volume", "")),
                    cumulative_value=_integer(raw.get("cumulative_value", "")),
                    individual_net_buy_shares=investor_values["individual"],
                    foreign_net_buy_shares=investor_values["foreign"],
                    institution_net_buy_shares=investor_values["institution"],
                    financial_investment_net_buy_shares=investor_values[
                        "financial_investment"
                    ],
                    insurance_net_buy_shares=investor_values["insurance"],
                    investment_trust_net_buy_shares=investor_values["investment_trust"],
                    other_finance_net_buy_shares=investor_values["other_finance"],
                    bank_net_buy_shares=investor_values["bank"],
                    pension_net_buy_shares=investor_values["pension"],
                    private_fund_net_buy_shares=investor_values["private_fund"],
                    state_net_buy_shares=investor_values["state"],
                    other_corporation_net_buy_shares=investor_values[
                        "other_corporation"
                    ],
                    domestic_foreign_net_buy_shares=investor_values[
                        "domestic_foreign"
                    ],
                    raw_json=json.dumps(raw, ensure_ascii=False, sort_keys=True),
                    request_name=request_name,
                    tr_code=str(payload.get("tr_code", TR_CODE)),
                    screen_no=str(payload.get("screen_no", screen_no)),
                    previous_next=str(payload.get("previous_next", "")),
                )
            )
        if not records:
            raise RuntimeError(f"no valid Kiwoom investor-flow rows returned for {ticker}")
        return records


def collect_investor_flows(
    *,
    symbols: tuple[str, ...],
    reference_date: str,
    limit: int,
    timeout_seconds: int,
    exporter_factory: Any = KiwoomInvestorFlowExporter,
) -> tuple[list[InvestorFlowRecord], KiwoomInvestorFlowExporter]:
    exporter = exporter_factory(timeout_seconds=timeout_seconds)
    exporter.login()
    records: list[InvestorFlowRecord] = []
    for index, ticker in enumerate(symbols):
        records.extend(
            exporter.investor_flows(
                ticker,
                screen_no=f"{9300 + index:04d}",
                reference_date=reference_date,
                limit=limit,
            )
        )
    return records, exporter


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("cannot write empty investor-flow CSV")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _snapshot_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_export(
    *,
    output_root: Path,
    reference_date: str,
    symbols: tuple[str, ...],
    limit: int,
    records: list[InvestorFlowRecord],
    exporter: KiwoomInvestorFlowExporter,
) -> tuple[InvestorFlowManifest, Path]:
    captured_at = datetime.now().astimezone()
    rows = [asdict(record) for record in records]
    snapshot_id = _snapshot_id(
        {
            "provider": PROVIDER,
            "source_scope": SOURCE_SCOPE,
            "captured_at": captured_at.isoformat(),
            "reference_date": reference_date,
            "symbols": list(symbols),
            "records": rows,
        }
    )
    directory = output_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%z") + f"__{snapshot_id[:12]}"
    )
    csv_path = directory / "investor_flows.csv"
    manifest_path = directory / "manifest.json"
    latest_path = output_root / "latest_investor_flow_export.json"
    _write_csv(csv_path, rows)
    warnings = (
        "Only the first OPT10059 response page is collected.",
        "Provider field names are mapped, but live response semantics are not yet certified.",
        "No 5-day/20-day aggregation, signal, score, or investment direction is produced.",
    )
    manifest = InvestorFlowManifest(
        schema_version="1.0",
        status="completed",
        provider=PROVIDER,
        source_scope=SOURCE_SCOPE,
        semantic_status=SEMANTIC_STATUS,
        snapshot_id=snapshot_id,
        captured_at=captured_at.isoformat(),
        reference_date=reference_date,
        symbols=symbols,
        record_count=len(records),
        limit_per_symbol=limit,
        tr_code=TR_CODE,
        request_mode="net_buy_quantity_single_share",
        amount_quantity_type="2",
        trade_type="0",
        unit_type="1",
        first_page_only=True,
        account_api_enabled=False,
        holdings_api_enabled=False,
        balance_api_enabled=False,
        order_api_enabled=False,
        decision_score_enabled=False,
        warnings=warnings,
        provider_messages=exporter.provider_messages,
    )
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    latest_payload = {
        "status": manifest.status,
        "provider": manifest.provider,
        "source_scope": manifest.source_scope,
        "semantic_status": manifest.semantic_status,
        "snapshot_id": manifest.snapshot_id,
        "export_directory": str(directory),
        "manifest_path": str(manifest_path),
        "investor_flows_path": str(csv_path),
        "record_count": manifest.record_count,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "decision_score_enabled": False,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(latest_payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="ascii",
    )
    return manifest, directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export read-only Kiwoom OPT10059 investor net-buy quantity evidence"
    )
    parser.add_argument("--symbols", nargs="+", default=["005930", "000660"])
    parser.add_argument("--reference-date", default="")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        symbols = _validate_symbols(args.symbols)
        reference_date = args.reference_date.strip() or datetime.now().strftime("%Y%m%d")
        if not _DATE.fullmatch(reference_date):
            raise ValueError("reference_date must use YYYYMMDD")
        records, exporter = collect_investor_flows(
            symbols=symbols,
            reference_date=reference_date,
            limit=args.limit,
            timeout_seconds=args.timeout_seconds,
        )
        manifest, directory = write_export(
            output_root=args.output_root,
            reference_date=reference_date,
            symbols=symbols,
            limit=args.limit,
            records=records,
            exporter=exporter,
        )
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print("KIWOOM OPENAPI+ INVESTOR FLOW EXPORT: FAIL", file=sys.stderr)
        print(f"failure: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("KIWOOM OPENAPI+ INVESTOR FLOW EXPORT: PASS")
        print(f"snapshot: {manifest.snapshot_id}")
        print(f"symbols: {', '.join(manifest.symbols)}")
        print(f"records: {manifest.record_count}")
        print(f"semantic status: {manifest.semantic_status}")
        print("decision score: disabled")
        print("account/holdings/balance/order APIs: disabled")
        print(f"export directory: {directory}")
    _flush_and_hard_exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
