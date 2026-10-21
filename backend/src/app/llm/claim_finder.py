"""Stage 1a: pull every distinct falsifiable claim out of one source (video transcript or blog
article) — asset, the claim itself, an optional condition/trigger, and structured reasoning.
Source-agnostic: the prompt
doesn't care whether the text came from a transcript or an article body, only the
text-extraction step upstream of this differs per source type (see CLAUDE.md).

Uses adaptive thinking: separating distinct claims and building out the reasoning fields,
and best-guessing a horizon when the analyst never stated a timeframe takes real judgment across
what can be a long, rambling source — not mechanical extraction."""

from datetime import date

from app.config import get_settings
from app.llm.client import parse_structured
from app.llm.schemas import ClaimExtractionList


CLAIM_FINDER_SYSTEM_PROMPT = """\
You read one piece of finance content (a video transcript or a blog post) from a market analyst and extract the most important, actionable claims the source is making, including the supporting reasoning. Return exactly as many claims as the source supports, no more and no less. Try not to create duplicate claims unless the claims being made are very different.
Two claims are only duplicates if they're about the same asset and predict essentially the same outcome. A claim about a different asset is never a duplicate, even if it shares the same underlying reasoning or warrant as another claim in the source — e.g. "the economy avoids recession" and "so the stock market keeps rallying" are two separate claims (different assets), not one claim restated. Extract both.
Only extract claims whose subject is a specific tradeable instrument (a stock, commodity, cryptocurrency, or ETF) or the broad macro economy's status (recession, bull market, bear market, inflation, rates, etc.). Skip claims whose real subject is a third party's behavior — a country, central bank, or institution buying/selling/reallocating something (e.g. "China will continue moving money out of US dollars and Treasuries into gold, euros, pounds, and European sovereign debt") — that's a capital-flow observation, not a trading-relevant prediction, even when phrased as something that will continue into the future. If the analyst goes on to state what that flow means for a specific instrument's price or the broader economy, extract that price/macro claim instead — not the flow narrative itself.

The claim's predicted *outcome* also has to be trading-relevant on its own — a price/valuation level, a buy/hold/sell/avoid decision, or macro-economy status — not a business or operational metric (revenue growth rate, customer/user count, margin, market share, EPS, a fundamental ratio like P/E) even when it's about a tradeable instrument and even when it's falsifiable in its own right. Analysts routinely build a price thesis out of several of these metric projections (e.g. "commercial revenue will 10x," "customers will grow to 70,000," "the P/E will compress to 40x") — capture each one as a ground, warrant, or backing entry on the price/trading claim it's supporting, not as its own separate claim. Only promote a metric projection to its own claim if the analyst gives it with no accompanying price or trading-relevant claim anywhere else in the source for it to support.

For each claim, return `suggested_ticker` as a list of one or more best-guess Yahoo Finance tickers. Use null when no clean tradeable instrument applies. Grounds and warrant are required: include at least one source-based ground and at least one inference connecting the ground(s) to the claim. Do not invent either field; when the source gives little support, capture the closest explicit fact and inference available.

1) Claim: The claim the analyst is making about the future, NOT about what caused the present. State only what the analyst actually predicts will happen — do not invent or infer an actionable conclusion they didn't give. This claim should be resolvable in the future by looking at stock/ crypto/ commodity prices, current events, and the rest of the claim (see rebuttals).
 Example: Investing in Bitcoin may see some short term volatility, but the long term will see gains.

1b) Stated implication (optional): Only if the analyst explicitly tells the audience what to do as a result of this claim (buy, hold, avoid, be cautious, etc.), capture that instruction in their own words here. Leave this empty if they only state the prediction and never say what to do about it — do not invent one just because the claim seems to imply it.
 Example: Investing in or holding Bitcoin is a good idea in the long term.

2) Condition / trigger: the discrete, checkable event that must happen before the claim's outcome is even testable — not the analyst's interpretive framing for why that event would matter. Most claims are direct/unconditional — leave this empty unless the analyst actually frames the claim as contingent on something else happening first. Give one or more when it applies.
Stick to what actually has to happen (a rate decision, a price level, an economic report, an election result, etc.), not a subjective judgment call layered on top of it (e.g. a rate cut being "too soon"/"premature," a setup "mirroring" a prior cycle) — that interpretive reasoning belongs in warrant/backing, not in the condition itself.
Don't invent a timeframe for the condition to occur by ("within 6 months," etc.) even if the surrounding claim implies urgency — staleness deadlines for conditions are derived downstream, not part of this field.
Examples:
a) The Fed cuts rates at the next meeting.
b) Bitcoin breaks above $120k.
c) The Fed raises rates again after the current cutting cycle. (Not: "the Fed's rate cuts prove premature" — that's the analyst's label for what a later hike would mean, not a separate condition to verify.)

3) Grounds: the cited facts. Valuation multiples, positioning data, a chart pattern, a policy change, an earnings surprise. Give one or more.
Examples:
a) The Fed is expected to cut rates at the next meeting.
b) Jobless claims came back higher than expected last month.

4) Warrant: the inference rule(s) connecting grounds to claim. Give one or more.
Examples:
a) When the Fed cuts rates, more money flows into risk assets such as Bitcoin over a longer time horizon.
b) Due to unemployment being higher, some people may sell risk assets like Bitcoin to cover everyday expenses

5) Backing: why the warrant holds. Historical base rates, a causal mechanism, theory, or just authority ("I called 2008"). Give one or more.
Examples:
a) Look at the last bull run
b) Review the causes for X downtrend

6) Qualifier: How certain are they of this? Qualitatively answer this in a sentence, and give a quantitative certainty value:
- virtually certain: 90-99%
- very likely / highly probable: 75-90%
- likely / probably: 55-75%
- roughly even chance: 45-55%
- unlikely: 25-45%
- very unlikely: 5-25%
- remote: 1-5%

7) Rebuttal / invalidation: what would prove the claim incorrect, what the user should watch out for as something that would invalidate the claim. Give one or more.
Examples:
a) If the fed hikes rates instead of cutting them, we wont necessarily see more money flow to risk assets.
b) If the next jobless claims report comes back showing labor market improvement, we may not see a Bitcoin pullback in the short term.

8) Horizon: the character of the claim's timeframe — one of:
- short-term: days to a few weeks
- swing: roughly 1-12 months
- long-term: 12+ months, but not framed as a multi-year thesis
- structural: a multi-year secular thesis, not tied to a specific date
Prefer the analyst's own stated timeframe when they give one. If they don't state one explicitly, make your best guess from the tone and framing of the piece instead of skipping it — e.g. a rapid-fire trading call reads as short-term/swing, a thesis-driven segment about where an asset is headed over the years reads as structural.

"""


def build_user_content(
    *, title: str, published_at: date | None, fetched_at: date, source_text: str
) -> str:
    """The user turn this pass sends. Public so the prompt lab can reproduce it exactly: a
    prompt tuned against different input than production sends would not transfer."""
    date_line = (
        f"Published date: {published_at.isoformat()}"
        if published_at is not None
        else f"Published date: unknown — use {fetched_at.isoformat()} (the date this source "
        "was pulled in) as the reference date for computing timeframes instead."
    )
    return f"Title: {title}\n{date_line}\n\nSource text:\n{source_text}"


def extract_claims(
    *,
    title: str,
    published_at: date | None,
    fetched_at: date,
    source_text: str,
    system_prompt: str | None = None,
    model: str | None = None,
) -> ClaimExtractionList:
    """`title` is the video/post title, included so the model has whatever framing the analyst
    themselves gave the piece (e.g. an explicit ticker or thesis in the title that the spoken
    transcript never restates). `published_at` is null for sources where it couldn't be
    determined (see Source model); `fetched_at` (when this source was ingested) is the fallback
    reference date for computing timeframes in that case — always available, so this never has
    to guess.

    `system_prompt`/`model` override CLAIM_FINDER_SYSTEM_PROMPT and the configured model for one
    call. Production callers leave both null; they exist so the prompt lab (../promptlab) can run
    an edited prompt through this exact function rather than reimplementing the pass."""
    settings = get_settings()
    return parse_structured(
        model=model or settings.claim_finder_model,
        system=system_prompt or CLAIM_FINDER_SYSTEM_PROMPT,
        user_content=build_user_content(
            title=title, published_at=published_at, fetched_at=fetched_at, source_text=source_text
        ),
        schema=ClaimExtractionList,
        # Thinking eats into the budget before the final structured answer — see module
        # docstring for why this pass needs it despite looking mechanical on the surface.
        max_tokens=16000,
        thinking=True,
    )
