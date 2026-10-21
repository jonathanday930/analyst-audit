import re

_ALIASES = {
    "s&p 500": "SPY", "s&p": "SPY", "spy": "SPY", "the market": "SPY",
    "the economy": "SPY", "us stocks": "SPY", "nasdaq": "QQQ", "qqq": "QQQ", "dow jones": "DIA",
    "the dow": "DIA", "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD", "crude oil": "CL=F",
    "oil prices": "CL=F", "oil price": "CL=F", "gold": "GC=F",
    "silver": "SI=F", "natural gas": "NG=F",
}
_ALIAS_KEYS_BY_LENGTH = sorted(_ALIASES, key=len, reverse=True)
_TICKER_SHAPE_RE = re.compile(r"^[A-Z0-9.=^-]{1,10}$")


def resolve_tickers(*, asset_description: str, suggested_ticker: str | list[str] | None) -> list[str]:
    """Every distinct, well-shaped ticker this claim/stance resolves to, in the order the model
    gave them. `suggested_ticker` always wins over the alias table below: the model already
    reasoned about the specific instrument(s) actually named in the source, and a claim can
    legitimately name more than one — a basket of specific stocks ("gold mining stocks, e.g.
    Agnico Eagle, Franco-Nevada" -> AEM, FNV, GDX; "the Magnificent 7" -> seven tickers) or a
    relative comparison between two ("QQQ relative to SCHD" -> both). The alias table is only a
    fallback for when the analyst named no specific instrument at all (a bare "the economy" or
    "gold" mention with nothing else to go on) — it must never override a good suggested_ticker
    list just because one of its phrases (e.g. "gold" inside "gold mining stocks", "s&p 500"
    inside a description of the Magnificent 7) happens to appear in the asset description."""
    candidates = [suggested_ticker] if isinstance(suggested_ticker, str) else (suggested_ticker or [])
    resolved: list[str] = []
    for candidate in candidates:
        normalized_candidate = candidate.strip().upper()
        if _TICKER_SHAPE_RE.match(normalized_candidate) and normalized_candidate not in resolved:
            resolved.append(normalized_candidate)
    if resolved:
        return resolved
    normalized = asset_description.lower()
    for phrase in _ALIAS_KEYS_BY_LENGTH:
        if phrase in normalized:
            return [_ALIASES[phrase]]
    return []


def resolve_ticker(*, asset_description: str, suggested_ticker: str | list[str] | None) -> str | None:
    """Single-ticker convenience wrapper over `resolve_tickers`, for callers (stances, which are
    always about one instrument) that only ever want the first/primary one."""
    resolved = resolve_tickers(asset_description=asset_description, suggested_ticker=suggested_ticker)
    return resolved[0] if resolved else None
