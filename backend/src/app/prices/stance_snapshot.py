"""Deterministic, non-LLM enrichment for stances (positions and broad sentiment reads): given a
resolved ticker and the date a stance was made, pulls real price history and reports what
actually happened since — current price, high/low since the call, and % change — so a stance can
be checked against reality without spending an LLM call on it. See "Stance market snapshot" in
CLAUDE.md.

Deliberately produces descriptive stats only, no good/bad verdict or scoring: stances are still
never resolved/graded individually (see the Stance schema section in CLAUDE.md) — this just
gives a human reader, and eventually meta-analyst analysis, real numbers to reason from.
"""

from datetime import date

from app.llm.schemas import StanceExtraction, StanceMarketSnapshot
from app.prices.price_data import fetch_price_series
from app.prices.ticker_resolver import resolve_ticker


def resolve_stance_ticker(stance: StanceExtraction) -> str | None:
    """Positions carry `asset_description`; broad sentiment carries `scope` instead (e.g. "the
    economy", "the market", "crypto generally") — both are just free text, so they go through
    the same alias/ticker-shape resolution claim finder's tickers already use."""
    description = stance.asset_description or stance.scope
    if not description:
        return None
    return resolve_ticker(asset_description=description, suggested_ticker=stance.suggested_ticker)


def compute_stance_snapshot(*, ticker: str, call_date: date, as_of: date) -> StanceMarketSnapshot | None:
    """None when call_date is in the future or no price data could be fetched (bad ticker,
    market closed the whole window, etc.) — callers should treat that as "no snapshot
    available" rather than an error."""
    if call_date > as_of:
        return None
    series = fetch_price_series(ticker=ticker, start=call_date, end=as_of)
    if series is None or not series.points:
        return None

    points = series.points
    call_price = points[0].close
    current_price = points[-1].close
    high_point = max(points, key=lambda p: p.close)
    low_point = min(points, key=lambda p: p.close)

    return StanceMarketSnapshot(
        ticker=ticker,
        call_date=call_date,
        as_of=as_of,
        days_since_call=(as_of - call_date).days,
        call_price=call_price,
        current_price=current_price,
        high_since_call=high_point.close,
        high_date=high_point.date,
        low_since_call=low_point.close,
        low_date=low_point.date,
        change_since_call_pct=((current_price - call_price) / call_price * 100) if call_price else 0.0,
    )
