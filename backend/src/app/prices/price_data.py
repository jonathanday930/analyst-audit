from dataclasses import dataclass
from datetime import date, timedelta

import yfinance as yf


@dataclass
class PricePoint:
    date: date
    close: float


@dataclass
class PriceSeries:
    ticker: str
    points: list[PricePoint]


def fetch_price_series(*, ticker: str, start: date, end: date) -> PriceSeries | None:
    try:
        frame = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), progress=False, multi_level_index=False, auto_adjust=True)
    except Exception:
        return None
    if frame is None or frame.empty or "Close" not in frame.columns:
        return None
    points = [PricePoint(date=index.date(), close=float(close)) for index, close in frame["Close"].items() if close == close]
    return PriceSeries(ticker=ticker, points=points) if points else None
