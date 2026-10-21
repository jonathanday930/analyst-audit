from datetime import date

from app.llm.schemas import StanceExtraction
from app.prices import stance_snapshot
from app.prices.price_data import PricePoint, PriceSeries
from app.prices.stance_snapshot import compute_stance_snapshot, resolve_stance_ticker


def _position(asset_description: str) -> StanceExtraction:
    return StanceExtraction(
        kind="position",
        asset_description=asset_description,
        suggested_ticker=None,
        direction="long",
        sentiment=None,
        scope=None,
        supporting_quotes=["I have a position in it"],
    )


def _sentiment(scope: str) -> StanceExtraction:
    return StanceExtraction(
        kind="sentiment",
        asset_description=None,
        suggested_ticker=None,
        direction=None,
        sentiment="bullish",
        scope=scope,
        supporting_quotes=["things will improve"],
    )


def test_resolve_stance_ticker_uses_asset_description_or_scope() -> None:
    assert resolve_stance_ticker(_position("gold")) == "GC=F"
    assert resolve_stance_ticker(_sentiment("the economy")) == "SPY"
    assert resolve_stance_ticker(_sentiment("purple unicorn mood")) is None


def test_compute_stance_snapshot_reports_high_low_and_change(monkeypatch) -> None:
    series = PriceSeries(
        ticker="GC=F",
        points=[
            PricePoint(date=date(2026, 6, 1), close=100.0),
            PricePoint(date=date(2026, 6, 15), close=90.0),
            PricePoint(date=date(2026, 7, 1), close=120.0),
            PricePoint(date=date(2026, 7, 15), close=110.0),
        ],
    )
    monkeypatch.setattr(stance_snapshot, "fetch_price_series", lambda **kwargs: series)

    snapshot = compute_stance_snapshot(ticker="GC=F", call_date=date(2026, 6, 1), as_of=date(2026, 7, 15))

    assert snapshot is not None
    assert snapshot.call_price == 100.0
    assert snapshot.current_price == 110.0
    assert snapshot.high_since_call == 120.0
    assert snapshot.high_date == date(2026, 7, 1)
    assert snapshot.low_since_call == 90.0
    assert snapshot.low_date == date(2026, 6, 15)
    assert snapshot.change_since_call_pct == 10.0


def test_compute_stance_snapshot_none_when_call_date_in_future() -> None:
    assert compute_stance_snapshot(ticker="SPY", call_date=date(2026, 12, 1), as_of=date(2026, 9, 3)) is None


def test_compute_stance_snapshot_none_when_no_price_data(monkeypatch) -> None:
    monkeypatch.setattr(stance_snapshot, "fetch_price_series", lambda **kwargs: None)
    assert compute_stance_snapshot(ticker="BAD", call_date=date(2026, 6, 1), as_of=date(2026, 7, 1)) is None
