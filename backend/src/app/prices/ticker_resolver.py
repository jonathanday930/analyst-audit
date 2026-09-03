import re

_ALIASES = {
    "s&p 500": "SPY", "s&p": "SPY", "spy": "SPY", "the market": "SPY",
    "us stocks": "SPY", "nasdaq": "QQQ", "qqq": "QQQ", "dow jones": "DIA",
    "the dow": "DIA", "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD", "crude oil": "CL=F",
    "oil prices": "CL=F", "oil price": "CL=F", "gold": "GC=F",
    "silver": "SI=F", "natural gas": "NG=F",
}
_ALIAS_KEYS_BY_LENGTH = sorted(_ALIASES, key=len, reverse=True)
_TICKER_SHAPE_RE = re.compile(r"^[A-Z0-9.=^-]{1,10}$")


def resolve_ticker(*, asset_description: str, suggested_ticker: str | None) -> str | None:
    normalized = asset_description.lower()
    for phrase in _ALIAS_KEYS_BY_LENGTH:
        if phrase in normalized:
            return _ALIASES[phrase]
    if suggested_ticker and _TICKER_SHAPE_RE.match(suggested_ticker.strip().upper()):
        return suggested_ticker.strip().upper()
    return None
