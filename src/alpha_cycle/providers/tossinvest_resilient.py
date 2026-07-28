"""Resilient TossInvest price collection built on the safe compressed transport."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from alpha_cycle.providers.tossinvest import (
    MAX_PRICE_SYMBOLS,
    CandleBatch,
    HttpResponse,
    MarketPrice,
    PriceBatch,
    _aware_datetime,
    _decimal,
    _mapping,
    _sequence,
    _text,
)
from alpha_cycle.providers.tossinvest_compressed import (
    TossInvestReadOnlyClient as _CompressedTossInvestReadOnlyClient,
)

MAX_PARTIAL_PRICE_FALLBACKS = 10
_SAFE_QUERY_KEYS = ("symbol", "symbols", "interval", "count", "adjusted", "before")


def _normalize_symbol(value: object, field_name: str) -> str:
    """Normalize KRX numeric symbols while preserving US and other valid tickers."""
    symbol = _text(value, field_name).upper()
    if symbol.isascii() and symbol.isdigit() and len(symbol) <= 6:
        return symbol.zfill(6)
    return symbol


def _requested_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(
        dict.fromkeys(
            _normalize_symbol(symbol, "requested symbol")
            for symbol in symbols
            if symbol.strip()
        )
    )
    if not normalized:
        raise ValueError("At least one symbol is required")
    if len(normalized) > MAX_PRICE_SYMBOLS:
        raise ValueError(
            f"TossInvest prices supports at most {MAX_PRICE_SYMBOLS} symbols"
        )
    return normalized


def _parse_price_payload(payload: object) -> list[MarketPrice]:
    container = _mapping(payload, "price response")
    rows = _sequence(container.get("result"), "price result")
    parsed: list[MarketPrice] = []
    seen: set[str] = set()
    for raw in rows:
        row = _mapping(raw, "price row")
        symbol = _normalize_symbol(row.get("symbol"), "price symbol")
        if symbol in seen:
            raise ValueError(
                f"TossInvest price response contains duplicate symbol: {symbol}"
            )
        seen.add(symbol)
        parsed.append(
            MarketPrice(
                symbol=symbol,
                timestamp=_aware_datetime(row.get("timestamp"), "price timestamp"),
                last_price=_decimal(row.get("lastPrice"), "last price"),
                currency=_text(row.get("currency"), "price currency").upper(),
            )
        )
    return parsed


def _mismatch_message(
    requested: set[str],
    returned: set[str],
    *,
    prefix: str,
) -> str:
    missing = sorted(requested - returned)
    unexpected = sorted(returned - requested)
    return (
        f"{prefix}: requested={sorted(requested)}, returned={sorted(returned)}, "
        f"missing={missing}, unexpected={unexpected}"
    )


def _safe_query_context(query: Mapping[str, str]) -> str:
    parts = [f"{key}={query[key]}" for key in _SAFE_QUERY_KEYS if key in query]
    return ",".join(parts) if parts else "none"


class TossInvestReadOnlyClient(_CompressedTossInvestReadOnlyClient):
    """Read-only client with bounded recovery and actionable safe diagnostics."""

    def _authorized_get(self, path: str, query: Mapping[str, str]) -> HttpResponse:
        try:
            return super()._authorized_get(path, query)
        except ValueError as exc:
            context = _safe_query_context(query)
            raise ValueError(f"{exc} endpoint={path} query={context}") from exc

    def prices(self, symbols: list[str] | tuple[str, ...]) -> PriceBatch:
        normalized = _requested_symbols(symbols)
        requested = set(normalized)
        bulk_response = self._authorized_get(
            "/api/v1/prices",
            {"symbols": ",".join(normalized)},
        )
        parsed = _parse_price_payload(bulk_response.payload)
        returned = {item.symbol for item in parsed}
        unexpected = returned - requested
        if unexpected:
            raise ValueError(
                _mismatch_message(
                    requested,
                    returned,
                    prefix="TossInvest price response contained unexpected symbols",
                )
            )

        missing = requested - returned
        if len(missing) > MAX_PARTIAL_PRICE_FALLBACKS:
            raise ValueError(
                _mismatch_message(
                    requested,
                    returned,
                    prefix=(
                        "TossInvest price response omitted too many symbols for safe "
                        "single-symbol fallback"
                    ),
                )
            )

        merged = {item.symbol: item for item in parsed}
        fallback_payloads: dict[str, object] = {}
        for symbol in sorted(missing):
            try:
                response = self._authorized_get(
                    "/api/v1/prices",
                    {"symbols": symbol},
                )
            except ValueError as exc:
                raise ValueError(
                    "TossInvest single-symbol price fallback failed: "
                    f"symbol={symbol}; {exc}"
                ) from exc
            single = _parse_price_payload(response.payload)
            single_symbols = {item.symbol for item in single}
            if single_symbols != {symbol} or len(single) != 1:
                raise ValueError(
                    _mismatch_message(
                        {symbol},
                        single_symbols,
                        prefix="TossInvest single-symbol fallback did not match",
                    )
                )
            merged[symbol] = single[0]
            fallback_payloads[symbol] = response.payload

        final_symbols = set(merged)
        if final_symbols != requested:
            raise ValueError(
                _mismatch_message(
                    requested,
                    final_symbols,
                    prefix="TossInvest price collection remained incomplete",
                )
            )

        raw_payload: object = bulk_response.payload
        response_headers = dict(bulk_response.headers)
        if fallback_payloads:
            raw_payload = {
                "bulk": bulk_response.payload,
                "fallback": fallback_payloads,
            }
            response_headers["X-Alpha-Cycle-Price-Fallback-Count"] = str(
                len(fallback_payloads)
            )
            response_headers["X-Alpha-Cycle-Price-Fallback-Symbols"] = ",".join(
                sorted(fallback_payloads)
            )

        ordered = tuple(merged[symbol] for symbol in sorted(merged))
        return PriceBatch(
            prices=ordered,
            raw_payload=raw_payload,
            response_headers=response_headers,
        )

    def candles(
        self,
        symbol: str,
        *,
        interval: str,
        count: int = 100,
        before: datetime | None = None,
        adjusted: bool = False,
    ) -> CandleBatch:
        normalized = _normalize_symbol(symbol, "candle symbol")
        try:
            return super().candles(
                normalized,
                interval=interval,
                count=count,
                before=before,
                adjusted=adjusted,
            )
        except ValueError as exc:
            raise ValueError(
                "TossInvest candle collection failed: "
                f"symbol={normalized}, interval={interval}, count={count}, "
                f"adjusted={str(adjusted).lower()}; {exc}"
            ) from exc
