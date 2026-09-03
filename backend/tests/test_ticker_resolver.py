from app.prices.ticker_resolver import resolve_ticker


def test_alias_and_suggestion_resolution() -> None:
    assert resolve_ticker(asset_description="the S&P 500", suggested_ticker=None) == "SPY"
    assert resolve_ticker(asset_description="semiconductor stocks", suggested_ticker="smh") == "SMH"
    assert resolve_ticker(asset_description="economy", suggested_ticker="not a ticker") is None
