"""Generate the cases the evals score: for each source, the claims plus the analyzer's result.

    evals/.venv/bin/python evals/generate.py [--fresh] [--video ID ...] [--force] [--skip-analyzer]

Per video this (1) takes the claim finder's claims (frozen Claude run by default, or --fresh to
call extract_claims again), then (2) runs the claim analyzer on EACH claim individually, with the
same ticker/price/benchmark inputs the real pipeline gives it. Everything is written to
cache/cases/<video_id>.json. Sequential on purpose (YouTube/yfinance rate limits; see
testing/README.md). Already-analyzed claims are skipped unless --force; the analyzer's answer
depends on today's date and the news, so re-run with --force to refresh it.
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import date, datetime, timezone

import common
from common import CASES_DIR, load_shortset
from app.llm.claim_analyzer import resolve_claim
from app.llm.claim_finder import extract_claims
from app.llm.schemas import ClaimContext, ClaimExtraction
from app.config import get_settings
from app.prices.price_data import PriceSeries, fetch_price_series
from app.prices.ticker_resolver import resolve_tickers


def _benchmark_ticker(ticker: str | None, asset_description: str) -> str:
    # Same coarse equity-vs-crypto heuristic as scripts/preview_pipeline.py.
    text = f"{ticker or ''} {asset_description}".lower()
    return "BTC-USD" if any(m in text for m in ("btc", "bitcoin", "eth", "ethereum", "crypto", "-usd")) else "SPY"


def summarize_series(series: PriceSeries | None) -> str:
    """The numbers a judge needs to check a rationale, without hundreds of daily rows."""
    if series is None or not series.points:
        return "no price data"
    pts = series.points
    hi = max(pts, key=lambda p: p.close)
    lo = min(pts, key=lambda p: p.close)
    first, last = pts[0], pts[-1]
    pct = (last.close / first.close - 1) * 100
    return (
        f"{series.ticker}: start {first.date} ${first.close:.2f}; end {last.date} ${last.close:.2f} ({pct:+.1f}%); "
        f"high {hi.date} ${hi.close:.2f}; low {lo.date} ${lo.close:.2f}; {len(pts)} trading days"
    )


def analyze_claim(claim: dict, *, published_at: date | None, as_of: date) -> dict:
    extraction = ClaimExtraction.model_validate(claim)
    tickers = resolve_tickers(asset_description=extraction.asset_description, suggested_ticker=extraction.suggested_ticker)
    start = published_at or as_of
    series = [s for t in tickers if (s := fetch_price_series(ticker=t, start=start, end=as_of)) is not None] if start <= as_of else []
    bench_ticker = _benchmark_ticker(tickers[0] if tickers else None, extraction.asset_description)
    bench = fetch_price_series(ticker=bench_ticker, start=start, end=as_of) if start <= as_of else None
    context = ClaimContext(
        asset_description=extraction.asset_description,
        suggested_ticker=extraction.suggested_ticker,
        condition_trigger=extraction.condition_trigger,
        claim=extraction.claim,
        horizon=extraction.horizon,
        trigger_status="waiting" if extraction.condition_trigger else None,
        published_at=published_at,
    )
    resolution, used_search = resolve_claim(
        claim=context, as_of=as_of, price_series=series, benchmark_series=bench, benchmark_ticker=bench_ticker
    )
    return {
        "resolution": resolution.model_dump(mode="json"),
        "used_web_search": used_search,
        "evidence": [summarize_series(s) for s in series] + [f"benchmark {summarize_series(bench)}"],
        "resolved_tickers": tickers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true", help="re-run claim finder instead of using the frozen claims")
    parser.add_argument("--video", nargs="*", help="only these video ids")
    parser.add_argument("--force", action="store_true", help="redo claims that already have an analysis")
    parser.add_argument("--skip-analyzer", action="store_true", help="claim finder output only")
    args = parser.parse_args()

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    settings = get_settings()
    for row in load_shortset():
        if args.video and row["video_id"] not in args.video:
            continue
        path = CASES_DIR / f"{row['video_id']}.json"
        existing = json.loads(path.read_text()) if path.exists() and not args.fresh else None
        published = date.fromisoformat(row["published_at"]) if row["published_at"] else None
        if existing:
            video = existing
        else:
            claims = row["frozen_claims"]
            if args.fresh:
                claims = [c.model_dump() for c in extract_claims(title=row["title"], published_at=published, fetched_at=today, source_text=row["transcript"]).claims]
            video = {
                "channel": row["channel"], "video_id": row["video_id"], "title": row["title"], "url": row["url"],
                "published_at": row["published_at"], "transcript": row["transcript"],
                "claim_source": "fresh" if args.fresh else "frozen", "claim_finder_model": settings.claim_finder_model,
                "claims": [{"index": i, "claim": c, "analysis": None} for i, c in enumerate(claims)],
            }
        if not args.skip_analyzer:
            for item in video["claims"]:
                if item["analysis"] and not args.force:
                    continue
                try:
                    item["analysis"] = {**analyze_claim(item["claim"], published_at=published, as_of=today), "as_of": today.isoformat(), "model": settings.claim_analyzer_model}
                except Exception as exc:  # noqa: BLE001 -- recorded, other claims still run
                    item["analysis"] = {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
                print(f"{row['channel']} claim {item['index']}: {'error' if 'error' in item['analysis'] else item['analysis']['resolution']['outcome']}")
                path.write_text(json.dumps(video, indent=2, default=str))
        path.write_text(json.dumps(video, indent=2, default=str))
        print(f"{row['channel']}: {len(video['claims'])} claims -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
