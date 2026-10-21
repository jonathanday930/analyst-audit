from datetime import date

import pytest
from pydantic import ValidationError

from app.llm.schemas import (
    AnalystMetaAnalysis,
    ClaimCategorization,
    ClaimContext,
    ClaimExtraction,
    ClaimExtractionList,
    ClaimHistoryEntry,
    ClaimResolution,
    StanceExtraction,
    StanceExtractionList,
    StanceHistoryEntry,
)


def test_claim_extraction_allows_unconditional_and_open_ended_claims() -> None:
    claim = ClaimExtraction(
        asset_description="NVDA",
        suggested_ticker=["NVDA"],
        condition_trigger=[],
        claim="rallies to new highs",
        grounds=["continued earnings growth"],
        warrant=["Earnings growth should support higher prices."],
        backing=[],
        qualifier="likely",
        confidence=65,
        rebuttal_invalidation=["A material earnings slowdown would invalidate this."],
        horizon="long-term",
    )
    assert ClaimExtractionList(claims=[claim]).claims[0].asset_description == "NVDA"
    assert claim.confidence == 65


def test_claim_extraction_requires_grounds_and_warrant() -> None:
    with pytest.raises(ValidationError):
        ClaimExtraction(
            asset_description="Bitcoin",
            suggested_ticker=["BTC-USD"],
            condition_trigger=[],
            claim="rises",
            horizon="swing",
        )

    claim = ClaimExtraction(
        asset_description="Bitcoin",
        suggested_ticker=["BTC-USD"],
        condition_trigger=[],
        claim="rises",
        grounds=["Bitcoin adoption is increasing"],
        warrant=["Greater adoption should support higher demand"],
        horizon="swing",
    )
    assert claim.grounds == ["Bitcoin adoption is increasing"]
    assert claim.warrant == ["Greater adoption should support higher demand"]
    assert claim.confidence is None


def test_claim_extraction_rejects_confidence_above_99() -> None:
    with pytest.raises(ValidationError):
        ClaimExtraction(
            asset_description="Bitcoin",
            suggested_ticker=["BTC-USD"],
            condition_trigger=[],
            claim="rises",
            grounds=["Adoption is increasing"],
            warrant=["Increasing adoption should support demand"],
            confidence=100,
            horizon="swing",
        )


def test_claim_extraction_conditional_claim_round_trips() -> None:
    claim = ClaimExtraction(
        asset_description="regional bank stocks",
        suggested_ticker=["KRE", "XLF"],
        condition_trigger=["the Fed cuts rates at the next meeting"],
        claim="rallies 10%",
        grounds=["Rates are falling"],
        warrant=["Lower rates should support regional bank stocks"],
        horizon="swing",
    )
    dumped = claim.model_dump()
    assert claim.suggested_ticker == ["KRE", "XLF"]
    assert dumped["condition_trigger"] == ["the Fed cuts rates at the next meeting"]
    assert "target_window_start" not in dumped


def test_claim_extraction_requires_horizon() -> None:
    with pytest.raises(ValidationError):
        ClaimExtraction(
            asset_description="NVDA",
            suggested_ticker=["NVDA"],
            condition_trigger=[],
            claim="rallies to new highs",
        )


def test_stance_extraction_position_and_sentiment_variants() -> None:
    position = StanceExtraction(
        kind="position",
        asset_description="Bitcoin",
        suggested_ticker="BTC-USD",
        direction="long",
        sentiment=None,
        scope=None,
        supporting_quotes=["I added to my Bitcoin position today"],
    )
    sentiment = StanceExtraction(
        kind="sentiment",
        asset_description=None,
        suggested_ticker=None,
        direction=None,
        sentiment="bearish",
        scope="the broader market",
        supporting_quotes=["I'm cautious on this market right now"],
    )
    stances = StanceExtractionList(stances=[position, sentiment])
    assert stances.stances[0].direction == "long"
    assert stances.stances[1].sentiment == "bearish"


def test_claim_resolution_still_pending_has_no_verdict() -> None:
    resolution = ClaimResolution(
        outcome="still_pending",
        verdict=None,
        trigger_status="waiting",
        rationale="Condition hasn't happened yet and the deadline hasn't passed.",
        benchmark=None,
    )
    assert resolution.verdict is None
    assert resolution.outcome == "still_pending"


def test_claim_context_accepts_unconditional_claim_shape() -> None:
    context = ClaimContext(
        asset_description="SPY",
        suggested_ticker=["SPY"],
        condition_trigger=[],
        claim="declines 10%",
        horizon="swing",
        trigger_status=None,
        published_at=date(2026, 3, 1),
    )
    assert context.trigger_status is None


def test_analyst_meta_analysis_categorizes_without_computing_counts() -> None:
    analysis = AnalystMetaAnalysis(
        categorizations=[
            ClaimCategorization(claim_id="c1", category="crypto"),
            ClaimCategorization(claim_id="c2", category="macro/rates"),
        ],
        overall_summary="Strong on macro, weaker on individual crypto calls.",
        strengths=["Consistently right about Fed-driven macro moves"],
        weaknesses=["Overstates crypto rally magnitudes"],
        consistency_notes=None,
    )
    assert len(analysis.categorizations) == 2
    assert analysis.consistency_notes is None


def test_claim_history_entry_and_stance_history_entry_round_trip() -> None:
    claim = ClaimHistoryEntry(
        claim_id="c1",
        asset_description="SPY",
        condition_trigger=[],
        claim="declines 10%",
        horizon="swing",
        status="resolved",
        verdict="good",
        rationale="SPY fell 12% over the window.",
    )
    stance = StanceHistoryEntry(
        kind="position",
        asset_description="NVDA",
        direction="long",
        sentiment=None,
        scope=None,
        quotes=["I bought some NVDA today"],
        stated_at=date(2026, 3, 1),
    )
    assert claim.verdict == "good"
    assert stance.direction == "long"
