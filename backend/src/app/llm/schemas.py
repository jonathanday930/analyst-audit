"""Pydantic models used as structured-output schemas for the four extraction/evaluation passes
(claim finder, stance extractor, claim analyzer, meta-analyst analysis), plus the small
input-context models each pass's caller builds from already-persisted data.

Deliberately separate from `app/schemas.py` (the API-facing wire models, which are
`from_attributes`-mapped off the SQLAlchemy rows): these exist purely to constrain what Claude
returns and to describe each pass's own inputs. Whatever module eventually wires a pass into the
database (not built yet — see TASKS.md) is responsible for translating between the two; that
translation is deliberately not done here so this module stays usable if the DB schema changes
shape later.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Horizon = Literal["short-term", "swing", "long-term", "structural"]
Verdict = Literal["good", "bad", "ambiguous"]
TriggerStatus = Literal["waiting", "triggered", "expired"]
StanceKind = Literal["position", "sentiment"]
PositionDirection = Literal["long", "short", "exited"]
Sentiment = Literal["bullish", "neutral", "bearish", "uncertain"]


# --- Claim finder (stage 1a) ----------------------------------------------------------------


class ClaimExtraction(BaseModel):
    """One falsifiable claim plus structured reasoning context.

    Reasoning fields support review and future analysis. Grounds and warrant are required because they provide the minimum
    reasoning chain for a reviewable claim. Deliberately has no target-window/trigger-deadline/
    timeframe fields — `horizon` is the only timing signal this pass produces; concrete
    resolution dates, if needed, are a downstream concern, not something this pass computes.
    """

    asset_description: str = Field(
        description="The asset/instrument as described by the analyst, e.g. 'NVDA', 'the S&P "
        "500', 'regional bank stocks'."
    )
    suggested_ticker: list[str] | None = Field(
        description="One or more best-guess tickers usable with Yahoo Finance (e.g. ['NVDA'], "
        "['BTC-USD'], or ['GLD', 'GC=F']). Null if there's no clean tradeable instrument."
    )
    condition_trigger: list[str] = Field(
        default_factory=list,
        description="The IF-condition(s) that must occur before this claim's outcome is even "
        "testable, in the analyst's own words (e.g. 'the Fed cuts rates at the next meeting', "
        "'Bitcoin breaks above $120k'). Empty if the claim is a direct, unconditional "
        "prediction with nothing that has to happen first — most claims are unconditional."
    )
    claim: str = Field(
        description="What the analyst predicts will happen, in their own terms, e.g. 'rallies "
        "20% to new highs', 'breaks down to $150', 'stays range-bound'. The raw prediction only "
        "— do not fold in an actionable conclusion the analyst didn't actually state; see "
        "stated_implication for that."
    )
    stated_implication: str | None = Field(
        default=None,
        description="What the analyst explicitly told the audience to do as a result of this "
        "claim (buy, hold, avoid, be cautious, etc.), in their own words. Null if they only "
        "stated the prediction and never said what to do about it — never inferred or "
        "fabricated just because the claim seems to imply an action."
    )
    grounds: list[str] = Field(
        min_length=1,
        description="Short, source-based paraphrases of the facts or observations the analyst "
        "cites in support, such as valuation, positioning, chart patterns, policy changes, or "
        "earnings surprises. Give at least one; do not invent facts not present in the source."
    )
    warrant: list[str] = Field(
        min_length=1,
        description="The analyst's inference rule(s) connecting the grounds to the expected "
        "outcome. Give at least one inference rule connecting the grounds to the outcome."
    )
    backing: list[str] = Field(
        default_factory=list,
        description="Why the warrant holds according to the analyst: historical base rates, "
        "causal mechanisms, theory, or authority. Empty when none is provided."
    )
    qualifier: str | None = Field(
        default=None,
        description="Qualitative description of the analyst's expressed confidence, such as "
        "'likely' or 'roughly even chance'. Null when unclear."
    )
    confidence: float | None = Field(
        default=None,
        ge=1,
        le=99,
        description="Best-effort numeric percentage estimate of the analyst's expressed "
        "confidence, not the model's belief that the claim will happen. Null when unclear."
    )
    rebuttal_invalidation: list[str] = Field(
        default_factory=list,
        description="What would prove the claim wrong or invalidate its reasoning, preferably "
        "concrete conditions to watch. Empty when the source provides no rebuttal."
    )
    horizon: Horizon = Field(
        description="The character of the claim's timeframe: 'short-term' (days to a few "
        "weeks), 'swing' (roughly 1-12 months), 'long-term' (12+ months, not framed as a "
        "multi-year thesis), or 'structural' (a multi-year secular thesis, not tied to a "
        "specific date). Prefer the analyst's own stated timeframe when they gave one. If they "
        "didn't state one explicitly, make your best guess from the tone and framing of the "
        "piece instead of leaving this unset — e.g. a rapid-fire trading call reads as "
        "short-term/swing, a thesis-driven segment about where an asset is headed over the "
        "years reads as structural."
    )


class ClaimExtractionList(BaseModel):
    claims: list[ClaimExtraction]


# --- Stance/sentiment extractor (stage 1b) --------------------------------------------------


class StanceExtraction(BaseModel):
    kind: StanceKind
    asset_description: str | None = Field(
        description="For kind='position': the instrument they say they've personally traded/"
        "held, e.g. 'NVDA', 'Bitcoin'. For kind='sentiment', only set this when the sentiment "
        "is about one specific instrument rather than the market/a sector broadly (use `scope` "
        "for the broader case, not both)."
    )
    suggested_ticker: str | None = Field(
        description="Best-guess ticker for asset_description, same convention as claim finder. "
        "Null if not applicable."
    )
    direction: PositionDirection | None = Field(
        description="Only for kind='position': 'long', 'short', or 'exited' (they say they "
        "closed out of it). Null for kind='sentiment'."
    )
    sentiment: Sentiment | None = Field(
        description="Only for kind='sentiment': their coarse mood — 'bullish', 'neutral', "
        "'bearish', or 'uncertain'. Null for kind='position'."
    )
    scope: str | None = Field(
        description="Only for kind='sentiment', when it's not tied to one instrument: what the "
        "sentiment is about, e.g. 'the broader market', 'tech stocks', 'crypto generally'. Null "
        "for kind='position', and null when asset_description is set instead."
    )
    supporting_quotes: list[str] = Field(
        min_length=1,
        description="One or more short verbatim quotes from the source text that back up this "
        "stance — the actual words that led you to extract it, not a paraphrase, so a human "
        "reviewer can check the extraction directly against the source."
    )


class StanceExtractionList(BaseModel):
    stances: list[StanceExtraction]


# --- Stance market snapshot (deterministic, non-LLM enrichment) ------------------------------


class StanceMarketSnapshot(BaseModel):
    """Real price stats for one stance's resolved ticker, computed directly from price history —
    no LLM call, no verdict. Answers "what has this ticker actually done since the call was
    made" (current price, high/low since then, % change) so a position or broad-sentiment read
    can be checked against reality at near-zero cost. See "Stance market snapshot" in CLAUDE.md.
    Deliberately not a verdict/score: stances are still never resolved or graded individually
    (see the Stance schema section) — this just supplies the numbers, for a human reader now and
    meta-analyst analysis later."""

    ticker: str
    call_date: date = Field(description="The date the stance was made (source's published date).")
    as_of: date = Field(description="The date this snapshot was computed, i.e. 'today'.")
    days_since_call: int
    call_price: float = Field(description="Closing price on (or the next trading day at/after) call_date.")
    current_price: float = Field(description="Most recent closing price as of as_of.")
    high_since_call: float
    high_date: date
    low_since_call: float
    low_date: date
    change_since_call_pct: float = Field(description="Simple % change from call_price to current_price.")


# --- Claim analyzer (stage 2) ---------------------------------------------------------------


class BenchmarkComparison(BaseModel):
    benchmark_ticker: str = Field(
        description="The benchmark used, e.g. 'SPY' for equity-ish claims, 'BTC-USD' for "
        "crypto claims."
    )
    benchmark_return_pct: float = Field(
        description="The benchmark's simple % return over the same window used to judge the "
        "claim."
    )
    claim_return_pct: float | None = Field(
        description="The claim's own asset's simple % return over that window, if it has one "
        "comparable return figure. Null if the claim isn't naturally expressed as a return "
        "(e.g. a rates/yield call)."
    )
    beat_benchmark: bool | None = Field(
        description="Whether the claim's own return beat the benchmark's. Null if "
        "claim_return_pct is null."
    )


class ClaimResolution(BaseModel):
    """One check of one open claim. Because a conditional claim's IF-condition and its
    predicted outcome can resolve at different times (the condition may fire well before the
    outcome window arrives), a single check can update trigger_status without yet reaching a
    verdict — `outcome` and `trigger_status` are deliberately separate fields, not one enum."""

    outcome: Literal["resolved", "trigger_expired", "still_pending"] = Field(
        description="'resolved' if there's now enough information to grade the claim good/bad/"
        "ambiguous. 'trigger_expired' if this is a conditional claim whose derived trigger "
        "staleness deadline has "
        "passed with the condition never occurring — moot, not graded. 'still_pending' if "
        "nothing conclusive yet (before the target window, an open-ended claim with nothing "
        "new to report, or a conditional claim still waiting on its condition within deadline)."
    )
    verdict: Verdict | None = Field(
        description="Only set when outcome='resolved'. 'good' if the predicted outcome "
        "happened as the analyst framed it (direction, and magnitude if one was stated); 'bad' "
        "if it didn't, including a predicted move that just never showed up (flat is not a "
        "win); 'ambiguous' if the evidence is genuinely thin or conflicting."
    )
    trigger_status: TriggerStatus | None = Field(
        description="For a conditional claim (condition_trigger was set on the claim), its "
        "status after this check. Null for an unconditional claim."
    )
    rationale: str = Field(
        description="Plain-prose explanation citing the actual price numbers (when given) "
        "and/or what web search found. Make sure this agrees with outcome/verdict/"
        "trigger_status before answering."
    )
    benchmark: BenchmarkComparison | None = Field(
        description="Only include when a benchmark comparison is meaningful for this claim and "
        "outcome='resolved' (see system prompt) — null otherwise."
    )


class ClaimContext(BaseModel):
    """Everything claim_analyzer needs about one open claim — deliberately a plain input model,
    not the SQLAlchemy row, so this module stays decoupled from persistence."""

    asset_description: str
    suggested_ticker: list[str] | None
    condition_trigger: list[str]
    claim: str
    horizon: Horizon
    trigger_status: TriggerStatus | None
    published_at: date | None


# --- Meta-analyst analysis (stage 3) --------------------------------------------------------


class ClaimCategorization(BaseModel):
    claim_id: str = Field(
        description="Echo back the id of the claim this categorization is for, exactly as "
        "given in the input."
    )
    category: str = Field(
        description="A short label for the kind of call this is, in your own words, e.g. "
        "'crypto', 'macro/rates', 'individual large-cap tech stocks'. Reuse the same label "
        "across claims that belong together within this run."
    )


class AnalystMetaAnalysis(BaseModel):
    categorizations: list[ClaimCategorization] = Field(
        description="One entry per claim given in the input, in any order. Do not compute "
        "counts or ratios yourself — that's done afterward from these labels plus each claim's "
        "already-known verdict."
    )
    overall_summary: str = Field(
        description="A few plain-language sentences on this analyst's track record as a whole."
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Short, specific observations tied to what's actually in the data, e.g. "
        "'consistently right about Fed-driven macro moves' — not generic praise.",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Same, for what this analyst tends to get wrong or overstate.",
    )
    consistency_notes: str | None = Field(
        description="Only when stance context was provided: call out any notable gap between "
        "what they publicly claimed and the positions/sentiment they disclosed for themselves "
        "(e.g. called for a crash while staying personally long tech). Null if no stance "
        "context was given, or nothing notable stands out."
    )


class ClaimHistoryEntry(BaseModel):
    """One claim from an analyst's history, as meta-analyst analysis sees it."""

    claim_id: str
    asset_description: str
    claim: str
    horizon: Horizon
    status: Literal["open", "resolved", "expired"]
    verdict: Verdict | None
    rationale: str | None


class StanceHistoryEntry(BaseModel):
    """One stance from an analyst's history, as meta-analyst analysis sees it."""

    kind: StanceKind
    asset_description: str | None
    direction: PositionDirection | None
    sentiment: Sentiment | None
    scope: str | None
    quotes: list[str]
    stated_at: date | None
