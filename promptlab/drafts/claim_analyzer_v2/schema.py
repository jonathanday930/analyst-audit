"""Claim analyzer output schema, redesign draft v1.

Not wired into anything. Once it is agreed, these models replace the stage 2 section of
`backend/src/app/llm/schemas.py` and `resolve_claim` returns `ClaimAssessment` instead of the
current resolution model.

Two principles behind the shape:

1. **The model judges, code does arithmetic.** Prices, percentage changes, highs/lows, window
   dates and the benchmark comparison are all deterministic, so they are computed in code, passed
   in as input (see `input_contract.md`) and stored on the claim row directly. They are
   deliberately absent from this schema: asking the model to echo numbers back is a way to get
   hallucinated numbers into the database. The model's job is the judgment plus the prose.
2. **Status and verdict stay separate.** `status` is lifecycle (does this claim need looking at
   again), `verdict` is scoring (was the analyst right). `expired` and `unverifiable` are
   lifecycle outcomes with no verdict at all, which keeps a moot call out of the analyst's score
   instead of quietly counting as a miss.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

AssessmentStatus = Literal["resolved", "pending", "expired", "unverifiable"]
Verdict = Literal["correct", "partly_correct", "incorrect"]
ComponentVerdict = Literal["correct", "partly_correct", "incorrect", "pending", "unverifiable"]
TriggerStatus = Literal["not_applicable", "waiting", "triggered", "expired"]
VerdictBasis = Literal["price_data", "web_evidence", "both", "none"]
EvidenceKind = Literal["price", "news", "company_filing", "official_data", "other"]
ImpliedDirection = Literal["long", "short", "neither"]
RecheckIn = Literal["1_week", "1_month", "3_months", "at_window_end", "never"]
ReasonsVerdict = Literal["yes", "no", "unclear", "not_applicable"]
Timing = Literal["on_time", "late_within_grace", "late_beyond_grace", "not_applicable"]


class TriggerAssessment(BaseModel):
    """Only meaningful for conditional claims. A claim whose condition never fired is moot, not
    wrong, so this gates whether the outcome gets graded at all."""

    status: TriggerStatus
    condition: str | None = Field(
        default=None,
        description="Which of the claim's stated conditions this assessment is about, when the "
        "claim listed more than one. Null for unconditional claims.",
    )
    observed_on: date | None = Field(
        default=None,
        description="The date the condition actually occurred. Only for status='triggered'.",
    )
    evidence: str | None = Field(
        default=None,
        description="One line saying how the condition was confirmed or ruled out, with the "
        "figure or event that settled it. Null for unconditional claims.",
    )


class ClaimComponent(BaseModel):
    """One testable assertion inside a multi-part claim, graded on its own so a call that was
    half right does not collapse into a single misleading verdict. Empty list for the normal
    single-assertion case."""

    assertion: str = Field(description="The single assertion, restated plainly in under 20 words.")
    verdict: ComponentVerdict
    evidence: str = Field(
        description="One line with the number, date or event that settles this component."
    )


class EvidenceItem(BaseModel):
    """Everything the verdict rests on, itemised so a reviewer can check the call without
    re-running it, and so a stale or thin evidence base is visible rather than buried in prose."""

    fact: str = Field(description="The fact itself, stated in one line, with its figure if it has one.")
    kind: EvidenceKind
    observed_on: date | None = Field(
        default=None, description="Date the fact refers to. Null when genuinely undated."
    )
    url: str | None = Field(
        default=None,
        description="Required for anything found via web search. Null for facts read off the "
        "supplied price block.",
    )


class ClaimAssessment(BaseModel):
    """One pass of the claim analyzer over one claim. Re-run on a schedule while status is
    'pending'; the other three statuses are terminal."""

    status: AssessmentStatus = Field(
        description="Lifecycle: 'resolved' (the record settles it), 'pending' (window still open "
        "and the outcome still possible), 'expired' (a conditional claim whose trigger deadline "
        "passed unmet), 'unverifiable' (nothing could ever settle it)."
    )
    verdict: Verdict | None = Field(
        default=None,
        description="Set only when status='resolved'. 'partly_correct' means directionally right "
        "but well short of the stated magnitude, a multi-part claim with mixed components, or a "
        "correct call that landed past its grace period (see `timing`). Null for every other "
        "status: an expired or unverifiable claim scores nothing.",
    )
    headline: str = Field(
        max_length=140,
        description="One sentence, verdict first, carrying the single decisive number. The only "
        "line many readers will see.",
    )
    rationale: str = Field(
        description="Two to four sentences: what was predicted, what the record shows with dates "
        "and figures, and the one thing that decided the verdict."
    )
    trigger: TriggerAssessment
    timing: Timing = Field(
        default="not_applicable",
        description="When the outcome landed relative to the claim's deadline: 'on_time' (inside "
        "the window), 'late_within_grace' (past window_end but on or before grace_end, which does "
        "not cost the verdict), 'late_beyond_grace' (past grace_end, which drops 'correct' to "
        "'partly_correct'). 'not_applicable' when the outcome never happened, the claim is still "
        "pending, or there was no deadline to be late against. Kept separate from `verdict` so "
        "stage 3 can tell a bad market read apart from a bad calendar read.",
    )
    components: list[ClaimComponent] = Field(
        default_factory=list,
        description="Per-assertion verdicts for multi-part claims. Empty for single-assertion "
        "claims, which is most of them.",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Every fact the verdict rests on. Anything cited in the rationale appears "
        "here. Empty only when status='unverifiable'.",
    )
    verdict_basis: VerdictBasis = Field(
        description="Which evidence carried the decision, so a verdict resting entirely on news "
        "reporting can be told apart from one resting on price data."
    )
    implied_direction: ImpliedDirection = Field(
        description="Whether being right about this claim meant being long, short, or neither "
        "(rates, macro conditions, claims with no tradeable side). Code uses this to orient the "
        "benchmark comparison; it is a reading of the claim, not of the outcome."
    )
    evaluator_confidence: int = Field(
        ge=1,
        le=99,
        description="Confidence in this verdict, not the analyst's confidence in the claim. "
        "Below 60 whenever ambiguous wording forced a judgment call or the evidence is thin.",
    )
    uncertainty: str | None = Field(
        default=None,
        description="What is shaky about this verdict, in one line. Required when "
        "evaluator_confidence is below 60, null when the call is clean.",
    )
    interpretation_note: str | None = Field(
        default=None,
        description="The reading used, when the claim's wording was ambiguous enough that "
        "another reading would have produced a different verdict. Null otherwise.",
    )
    right_for_stated_reasons: ReasonsVerdict = Field(
        default="not_applicable",
        description="Whether the outcome arrived through the mechanism the analyst named or "
        "through something unrelated. Never affects the verdict; it feeds stage 3, which is "
        "where luck versus skill gets weighed.",
    )
    unresolved_reason: str | None = Field(
        default=None,
        description="Why this could not be settled. Required when status is 'pending' or "
        "'unverifiable', null otherwise.",
    )
    what_would_settle_it: str | None = Field(
        default=None,
        description="The specific observation that would resolve this claim on a later pass, "
        "e.g. 'a close above $120k' or 'the December FOMC decision'. Set when status='pending'.",
    )
    recheck_in: RecheckIn = Field(
        default="never",
        description="When this claim is worth looking at again. 'never' for every terminal "
        "status. Code turns this into a concrete next-check date; do not compute dates here.",
    )
