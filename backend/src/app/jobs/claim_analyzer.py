from datetime import date, datetime, timedelta, timezone

from app.db import crud
from app.db.session import SessionLocal
from app.llm.claim_analyzer import resolve_claim
from app.llm.schemas import ClaimContext
from app.prices.price_data import fetch_price_series
from app.prices.ticker_resolver import resolve_tickers


def _is_due(claim, today: date) -> bool:
    published = claim.source.published_at
    if published is None:
        return True
    if claim.condition_trigger and claim.trigger_status != "triggered":
        return today >= published + timedelta(days=365)
    starts = {"short-term": 7, "swing": 30, "long-term": 365, "structural": 0}
    return today >= published + timedelta(days=starts.get(claim.horizon or "structural", 0))


def _benchmark_for(asset_description: str) -> str | None:
    text = asset_description.lower()
    if any(word in text for word in ("bitcoin", "btc", "ethereum", "eth", "crypto")):
        return "BTC-USD"
    if any(word in text for word in ("rate", "yield", "bond", "treasury", "inflation")):
        return None
    return "SPY"


def run_claim_analyzer(*, as_of: date | None = None) -> int:
    """Resolve every due open claim, keeping one bad claim from aborting the batch."""
    today = as_of or date.today()
    processed = 0
    with SessionLocal() as db:
        for claim in crud.list_claims(db, status="open"):
            if claim.extraction_status != "complete" or not claim.claim or not claim.asset_description:
                continue
            if not _is_due(claim, today):
                continue
            tickers = resolve_tickers(asset_description=claim.asset_description, suggested_ticker=claim.suggested_ticker)
            start = claim.source.published_at or today
            asset_series = [fetch_price_series(ticker=ticker, start=start, end=today) for ticker in tickers]
            benchmark_ticker = _benchmark_for(claim.asset_description)
            benchmark_series = fetch_price_series(ticker=benchmark_ticker, start=start, end=today) if benchmark_ticker else None
            context = ClaimContext(
                asset_description=claim.asset_description,
                suggested_ticker=claim.suggested_ticker,
                condition_trigger=claim.condition_trigger,
                claim=claim.claim,
                horizon=claim.horizon or "structural",
                trigger_status=claim.trigger_status,
                published_at=claim.source.published_at,
            )
            try:
                resolution, _ = resolve_claim(
                    claim=context,
                    as_of=today,
                    price_series=[series for series in asset_series if series is not None],
                    benchmark_series=benchmark_series,
                    benchmark_ticker=benchmark_ticker,
                )
                status = "resolved" if resolution.outcome == "resolved" else "expired" if resolution.outcome == "trigger_expired" else "open"
                benchmark = resolution.benchmark.model_dump() if resolution.benchmark else None
                observed_at = datetime.now(timezone.utc) if resolution.trigger_status == "triggered" else None
                crud.update_claim_resolution(
                    db, claim=claim, verdict=resolution.verdict, rationale=resolution.rationale,
                    benchmark=benchmark, status=status, trigger_status=resolution.trigger_status,
                    trigger_observed_at=observed_at,
                )
                db.commit()
                processed += 1
            except Exception:
                db.rollback()
                continue
    return processed


if __name__ == "__main__":
    raise SystemExit(run_claim_analyzer())
