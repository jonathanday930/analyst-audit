"""Stage 2: the recurring re-check job. Resolves one open claim at a time using real historical
price data (when available) and web search for real-world-event conditions — see the Claim
analyzer stage description in CLAUDE.md.

Reuses the self-consistency instruction ("make sure your rationale agrees with the verdict
before answering") from `youtube_fact_checker`'s evaluation pass on purpose: that sibling
project observed Claude write a rationale contradicting its own verdict field on a conditional
claim, and fixed it with this instruction plus adaptive thinking. This pass has the same shape
of failure mode available to it (a conditional claim, a trigger-vs-outcome distinction) even
though that failure hasn't specifically been observed here yet — applying the known fix
preemptively rather than waiting to reproduce it."""

from datetime import date, timedelta

from app.config import get_settings
from app.llm.client import parse_structured_with_web_search
from app.llm.schemas import ClaimContext, ClaimResolution
from app.prices.price_data import PriceSeries

CLAIM_ANALYZER_SYSTEM_PROMPT = """\
You check one open claim from a finance analyst's track record and decide, as of today, whether \
enough is now known to grade it — using real historical price data (when it's provided) and web \
search for real-world news/events. Read everything you're given and reason honestly about \
whether the analyst's call panned out; don't force a verdict before there's enough to judge.

Conditional claims (condition_trigger is non-empty) need a two-step check:
1. Has the condition itself actually happened yet, per web search or the price data? If yes, \
report trigger_status='triggered'. If today is past the derived trigger staleness deadline (one \
year after publication) and the condition never happened, report trigger_status='expired' and \
outcome='trigger_expired' — this is moot, not a failed prediction, so do not set a verdict for \
it. If neither yet, report \
trigger_status='waiting' and outcome='still_pending'.
2. Only once the condition has triggered do you go on to judge the predicted outcome itself, \
exactly as you would for an unconditional claim below.

For an unconditional claim (condition_trigger is empty), or a conditional claim whose condition \
has already triggered:
- Use the rough target window derived from the horizon and publication date below. If today is \
before that window starts, or the claim is structural and nothing conclusive has happened yet, \
report outcome='still_pending' — leave verdict null and it'll be rechecked again later.
- Otherwise, report outcome='resolved' and pick a verdict:
  - 'good': the predicted outcome happened, in the direction (and magnitude, if one was stated) \
the analyst actually described.
  - 'bad': it didn't — including a predicted move that just never showed up (flat is not a win).
  - 'ambiguous': you genuinely can't tell, because the evidence is thin, conflicting, or \
missing. Use this sparingly, only when you truly cannot judge.

If benchmark price data is also given, compute whether the claim's own asset beat the \
benchmark's return over the same window and report it in `benchmark` — but this is a separate, \
additional signal, not part of the good/bad verdict itself: a call can be correct in isolation \
while still trailing the benchmark, and that distinction is exactly what this field is for. Skip \
it (leave `benchmark` null) if no benchmark data was given, or if the claim isn't naturally \
expressed as a comparable return (e.g. a rates/yield call).

The claim asset can come with more than one price series when the analyst named several \
instruments in one claim — a basket (e.g. several stocks grouped as "the Magnificent 7") or a \
relative comparison between two named instruments (e.g. "QQQ relative to SCHD"). When that \
happens, use every series given together: for a basket, judge the outcome against the group as \
a whole rather than any one member; for a relative comparison, judge it against the stated \
relationship between the two (which one moved more, in which direction), not either one's price \
in isolation.

Write a short, plain-prose rationale citing the actual numbers (when price data was given) \
and/or summarizing what web search found. Double-check that outcome/verdict/trigger_status all \
agree with your rationale before answering.\
"""


def _series_text(label: str, series: PriceSeries | None) -> str:
    if series is None or not series.points:
        return f"\nNo {label} price data is available — rely on web search for this part."
    lines = "\n".join(f"  {point.date.isoformat()}: ${point.close:.2f}" for point in series.points)
    return f"\n{label.capitalize()} daily closes for {series.ticker}:\n{lines}"


def _asset_series_text(series_list: list[PriceSeries]) -> str:
    """Same shape as `_series_text`, but for the claim asset, which can resolve to more than one
    ticker (a basket, or a relative comparison — see the system prompt). Each series gets its
    own labeled block so the model can tell them apart."""
    usable = [series for series in series_list if series.points]
    if not usable:
        return "\nNo claim asset price data is available — rely on web search for this part."
    return "".join(
        f"\nClaim asset daily closes for {series.ticker}:\n"
        + "\n".join(f"  {point.date.isoformat()}: ${point.close:.2f}" for point in series.points)
        for series in usable
    )


def _derived_window(horizon: str, published_at: date | None) -> tuple[str, str, str]:
    """Describe a deliberately rough resolution window from the only timing signals available."""
    ranges = {
        "short-term": (7, 28),
        "swing": (30, 365),
        "long-term": (365, 730),
        "structural": (730, None),
    }
    start_days, end_days = ranges[horizon]
    if published_at is None:
        return "unknown (publication date unavailable)", "unknown", "unknown"
    start = published_at + timedelta(days=start_days)
    end = published_at + timedelta(days=end_days) if end_days is not None else None
    return start.isoformat(), end.isoformat() if end else "open-ended", (published_at + timedelta(days=365)).isoformat()


def resolve_claim(
    *,
    claim: ClaimContext,
    as_of: date,
    price_series: list[PriceSeries],
    benchmark_series: PriceSeries | None = None,
    benchmark_ticker: str | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
) -> tuple[ClaimResolution, bool]:
    """Returns (resolution, used_web_search). `price_series` is a list because a claim can
    resolve to more than one ticker (a basket or a relative comparison — see
    `ticker_resolver.resolve_tickers` and the system prompt above); pass an empty list when
    nothing resolved. `benchmark_ticker` may be set even when `benchmark_series` is None (fetch
    failed) so the prompt can say so rather than silently omitting the comparison; pass neither
    to skip benchmarking this claim entirely.

    `system_prompt`/`model` override CLAIM_ANALYZER_SYSTEM_PROMPT and the configured model for
    one call. See extract_claims for why that seam exists."""
    settings = get_settings()

    claim_text = (
        f"Asset: {claim.asset_description}\n"
        f"Condition/trigger: {'; '.join(claim.condition_trigger) if claim.condition_trigger else 'none (unconditional claim)'}\n"
        f"Claim: {claim.claim}\n"
        f"Horizon: {claim.horizon}\n"
        "Derived rough target window from horizon/publication date: "
        f"{_derived_window(claim.horizon, claim.published_at)[0]} to {_derived_window(claim.horizon, claim.published_at)[1]}\n"
        f"Current trigger status: {claim.trigger_status or 'n/a (unconditional)'}\n"
        "Derived trigger staleness deadline (for conditional claims): "
        f"{_derived_window(claim.horizon, claim.published_at)[2]}\n"
        "Source published: "
        f"{claim.published_at.isoformat() if claim.published_at else 'unknown'}\n"
        f"Today's date: {as_of.isoformat()}\n"
    )

    price_text = _asset_series_text(price_series)
    if benchmark_series is not None:
        benchmark_text = _series_text(
            f"benchmark ({benchmark_ticker or benchmark_series.ticker})", benchmark_series
        )
    elif benchmark_ticker:
        benchmark_text = (
            f"\nBenchmark ticker {benchmark_ticker} was selected but no price data could be "
            "fetched for it."
        )
    else:
        benchmark_text = ""

    resolution, used_web_search = parse_structured_with_web_search(
        model=model or settings.claim_analyzer_model,
        system=system_prompt or CLAIM_ANALYZER_SYSTEM_PROMPT,
        user_content=claim_text + price_text + benchmark_text,
        schema=ClaimResolution,
        # Thinking + search results both eat into the budget before the final structured
        # answer, so this needs more headroom than a plain structured call.
        max_tokens=8192,
    )
    return resolution, used_web_search
