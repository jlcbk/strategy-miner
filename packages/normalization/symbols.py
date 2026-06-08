from __future__ import annotations

from dataclasses import dataclass

from packages.normalization.models import Exchange, MarketType


KNOWN_QUOTES = (
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "USD",
    "BTC",
    "ETH",
    "EUR",
    "TRY",
)


@dataclass(frozen=True)
class NormalizedSymbol:
    symbol: str
    base_asset: str
    quote_asset: str


def normalize_symbol(
    exchange: Exchange | str,
    raw_symbol: str,
    market_type: MarketType | str,
) -> NormalizedSymbol:
    exchange = Exchange(exchange)
    market_type = MarketType(market_type)
    raw = raw_symbol.upper().strip()

    if exchange == Exchange.OKX or "-" in raw:
        return _normalize_hyphen_symbol(raw, market_type)

    compact = raw.replace("/", "").replace("_", "")
    for quote in KNOWN_QUOTES:
        if compact.endswith(quote) and len(compact) > len(quote):
            base = compact[: -len(quote)]
            return NormalizedSymbol(symbol=f"{base}-{quote}", base_asset=base, quote_asset=quote)

    raise ValueError(f"无法从 symbol 推断 base/quote：{raw_symbol!r}")


def _normalize_hyphen_symbol(raw: str, market_type: MarketType) -> NormalizedSymbol:
    parts = raw.split("-")
    if len(parts) < 2:
        raise ValueError(f"无法从 symbol 推断 base/quote：{raw!r}")

    base = parts[0]
    quote = parts[1]

    if market_type == MarketType.PERP and len(parts) >= 3 and parts[2] == "SWAP":
        return NormalizedSymbol(symbol=f"{base}-{quote}", base_asset=base, quote_asset=quote)

    if market_type == MarketType.FUTURE and len(parts) >= 3:
        return NormalizedSymbol(
            symbol=f"{base}-{quote}-{parts[2]}",
            base_asset=base,
            quote_asset=quote,
        )

    if market_type == MarketType.OPTION and len(parts) >= 5:
        return NormalizedSymbol(
            symbol=f"{base}-{quote}-{parts[2]}-{parts[3]}-{parts[4]}",
            base_asset=base,
            quote_asset=quote,
        )

    return NormalizedSymbol(symbol=f"{base}-{quote}", base_asset=base, quote_asset=quote)
