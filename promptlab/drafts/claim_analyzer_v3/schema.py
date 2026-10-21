"""Draft output schema for the redesigned claim analyzer (v3).

Not wired in anywhere yet. Written fresh against the current claim-finder output
(`backend/scripts/output/shortset_claims/`), not derived from the committed
`ClaimResolution` in `app/llm/schemas.py`.

Two design choices drive the shape:

* **Field order is load bearing.** Structured output is generated top to bottom, so `test`
  comes first: the model has to commit to what would count as true before it sees itself
  writing an outcome. Inside `ClaimCheck` the same ordering applies, criterion before
  evidence before outcome. This is the main defence against retro-fitting the test to
  whatever the price data happened to do.
* **The model never does arithmetic.** Baselines, highs, lows, and percentage changes are
  computed in code from yfinance and handed to the model as facts (see
  `input_contract.md`). The model reads them, quotes them, and compares them to the
  threshold it extracted. `target_value` exists so code can independently re-check the
  model's price verdict.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal[
    "correct",
    "partly_correct",
    "incorrect",
    "too_early",
    "not_triggered",
    "unfalsifiable",
]
ResolutionStatus = Literal["resolved", "pending", "expired"]
TriggerState = Literal["not_applicable", "waiting", "triggered", "expired"]
Measure = Literal[
    "price_level",
    "percent_change",
    "relative_performance",
    "event_occurrence",
    "macro_indicator",
    "not_measurable",
]
TargetDirection = Literal["at_or_above", "at_or_below", "inside_range", "not_applicable"]
WindowBasis = Literal["stated_in_claim", "derived_from_horizon", "open_ended"]
EvidenceNeeded = Literal["price_only", "web_only", "price_and_web", "none_possible"]
CheckImportance = Literal["core", "secondary"]
CheckOutcome = Literal["met", "partly_met", "not_met", "too_early", "undetermined"]
ReasoningHeldUp = Literal["yes", "partly", "no", "unclear"]


class ClaimTest(BaseModel):
    """The operationalization of the claim, written before any outcome is looked at."""

    restated_claim: str = Field(
        description="One sentence stating what has to be true for this claim to count as "
        "correct: instrument, direction, number, deadline. Plain language."
    )
    interpretation_note: str | None = Field(
        default=None,
        description="How any vagueness in the claim was pinned down, including which default "
        "threshold from the prompt's table was applied and why that reading was chosen over a "
        "looser one. Null when the analyst's own wording was already explicit."
    )
    falsifiable: bool = Field(
        description="False only when no reading of the claim produces a decidable test, e.g. a "
        "claim about the analyst's own future behaviour or a quality judgment with no "
        "observable consequence in any window."
    )
    unfalsifiable_reason: str | None = Field(
        default=None,
        description="One sentence on why no decidable test exists. Null when falsifiable."
    )
    scenario_label: str | None = Field(
        default=None,
        description="Set when the source explicitly presented this claim as one of several "
        "labelled scenarios, e.g. 'bear case', 'base case', 'bull case'. Null otherwise."
    )
    measure: Measure = Field(
        description="What kind of quantity decides the claim."
    )
    subject_tickers: list[str] = Field(
        default_factory=list,
        description="The instrument(s) the claim is about, taken from the market data block. "
        "Usually one. Several when the claim is about a basket, e.g. the seven Magnificent 7 "
        "tickers. Empty when the claim has no tradeable subject, e.g. a recession call."
    )
    comparison_tickers: list[str] = Field(
        default_factory=list,
        description="The instrument(s) the subject is being measured against when the claim is "
        "relative, e.g. SCHD for 'QQQ will underperform SCHD'. Empty otherwise. Never the same "
        "ticker as a subject."
    )
    target_value: float | None = Field(
        default=None,
        description="The decisive numeric threshold, in the units of the measure: a price for "
        "price_level, a percentage for percent_change or relative_performance. For a range, "
        "the near end. Null when the claim has no numeric threshold."
    )
    target_upper: float | None = Field(
        default=None,
        description="The far end of a stated range. Null unless the claim named a range."
    )
    target_direction: TargetDirection = Field(
        description="Which side of target_value satisfies the claim."
    )
    window_start: date = Field(
        description="Normally the source's publication date. Later only when a trigger fired "
        "after publication, in which case use the trigger date."
    )
    window_end: date | None = Field(
        description="The deadline the claim has to be met by. Null for an open-ended structural "
        "claim."
    )
    window_basis: WindowBasis = Field(
        description="Whether window_end came from a date the analyst stated, from the horizon "
        "default, or is open ended."
    )
    evidence_needed: EvidenceNeeded = Field(
        description="What it takes to settle this claim: market data alone, web search alone, "
        "both, or neither because it is not decidable."
    )


class SourcedFact(BaseModel):
    """One externally verified fact the verdict rests on. Required for anything settled by
    search rather than by the market data block."""

    statement: str = Field(description="The fact itself, in one sentence, with its number.")
    observed_on: date | None = Field(
        description="The date the fact refers to, not the date the article was written. Null if "
        "the source does not make it clear."
    )
    publisher: str = Field(description="Who published it, e.g. 'BLS', 'Reuters'.")
    url: str = Field(description="Direct URL to the source.")


class ClaimCheck(BaseModel):
    """One separately decidable part of the claim. A composite claim gets several; a simple one
    gets a single core check. Field order is deliberate: the criterion is written before the
    evidence, and the evidence before the outcome."""

    criterion: str = Field(
        description="The explicit, quantified condition this check decides, e.g. 'gold trades "
        "at or above $3,500 at some point before 2025-12-31'."
    )
    importance: CheckImportance = Field(
        description="'core' if the claim stands or falls on this part, 'secondary' if it is a "
        "supporting detail. The verdict follows the core checks."
    )
    evidence: str = Field(
        description="What actually happened, with the real numbers and dates taken from the "
        "market data block or from sourced_facts. No arithmetic beyond comparison."
    )
    outcome: CheckOutcome = Field(
        description="'met', 'partly_met', 'not_met', 'too_early' if the window is still open, or "
        "'undetermined' if the evidence needed could not be obtained."
    )


class BenchmarkAssessment(BaseModel):
    """Whether the call beat simply holding the benchmark. Only present when the claim implies a
    comparable return, per CLAUDE.md's 'Evaluation includes a benchmark comparison'."""

    benchmark_ticker: str = Field(description="The benchmark used, from the market data block.")
    claim_return_pct: float = Field(
        description="Return on the claim's instrument over the window, copied from the market "
        "data block, not recomputed."
    )
    benchmark_return_pct: float = Field(
        description="Return on the benchmark over the same window, copied from the market data "
        "block."
    )
    beat_benchmark: bool = Field(
        description="True when the claim's instrument returned more than the benchmark over the "
        "window."
    )
    note: str = Field(
        description="One sentence on what that means for the call, e.g. 'right about the "
        "direction, but SPY returned more over the same period'."
    )


class ClaimResolution(BaseModel):
    """The claim analyzer's full output for one claim.

    Order matters: the test is committed to first, then the evidence is gathered, then the
    checks are decided, and only then is a verdict named and written up.
    """

    test: ClaimTest

    trigger_state: TriggerState = Field(
        description="'not_applicable' when the claim carried no condition. Otherwise whether the "
        "condition is still waiting, has fired, or expired unmet at its deadline."
    )
    trigger_observed_on: date | None = Field(
        default=None,
        description="The date the condition actually happened. Null unless trigger_state is "
        "'triggered'."
    )
    trigger_deadline: date | None = Field(
        default=None,
        description="The date the condition has to happen by, which is the claim's window_end "
        "unless the analyst gave the condition its own deadline. Null when not applicable."
    )
    trigger_evidence: str | None = Field(
        default=None,
        description="What shows the condition did or did not happen, with dates. Null when not "
        "applicable."
    )

    sourced_facts: list[SourcedFact] = Field(
        default_factory=list,
        description="Every externally verified fact the verdict rests on. Empty for a claim "
        "settled entirely by the market data block."
    )
    checks: list[ClaimCheck] = Field(
        min_length=1,
        description="One entry per separately decidable part of the claim, at least one of them "
        "'core'."
    )
    benchmark: BenchmarkAssessment | None = Field(
        default=None,
        description="Null when no comparable return applies, e.g. yields, macro status, or a "
        "claim about the analyst's own behaviour."
    )
    reasoning_held_up: ReasoningHeldUp = Field(
        description="Whether the mechanism the analyst gave is what actually produced the "
        "outcome. Recorded for the track record only; it never changes the verdict."
    )

    verdict: Verdict
    status: ResolutionStatus = Field(
        description="'resolved' for correct, partly_correct, incorrect and unfalsifiable; "
        "'pending' for too_early; 'expired' for not_triggered."
    )
    confidence: int = Field(
        ge=1,
        le=99,
        description="How sure you are of your own verdict given the evidence. Not the analyst's "
        "confidence, and not the probability the claim comes true."
    )
    summary: str = Field(
        description="Two to four sentences: what was claimed, what actually happened with real "
        "numbers and dates, and why that is the verdict. Plain language, no em dashes."
    )
    headline: str = Field(
        max_length=160,
        description="One sentence saying whether the analyst was right, naming the decisive "
        "number and date. No hedging, no jargon, no em dashes."
    )

    what_to_watch: list[str] = Field(
        default_factory=list,
        description="The specific observable things that would settle the claim. Required when "
        "the verdict is 'too_early'."
    )
    next_check_on: date | None = Field(
        default=None,
        description="When it is worth checking again. Required when the verdict is 'too_early'."
    )
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Anything needed and not obtained: a missing price series, a fact search "
        "could not confirm. Be specific."
    )
