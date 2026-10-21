"""The metrics. Three layers, each scored per individual claim:

  1. claim_accuracy_metrics: is this one extracted claim faithful to the transcript it came from?
     (LLM judge, one yes/no question each, strict so a score is pass/fail and a failure is
     explainable.)
  2. (the claim analyzer itself runs in generate.py; it is what produces a verdict per claim.)
  3. analyzer_metrics: is the analyzer's output for that claim sound? A code check for internal
     consistency plus LLM judges that see the claim, the price evidence it was given, and what
     it concluded.
"""

from __future__ import annotations

from datetime import date

from deepeval.metrics import BaseMetric, GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from app.llm.claim_analyzer import _derived_window
from judge_model import get_judge

P = SingleTurnParams


def _geval(name: str, criteria: str, params: list, threshold: float = 1.0) -> GEval:
    return GEval(name=name, criteria=criteria, evaluation_params=params, model=get_judge(), threshold=threshold, strict_mode=True)


# --- Layer 1: claim accuracy against the transcript ------------------------------------------
# INPUT is the full source; ACTUAL_OUTPUT is one extracted claim.

def claim_accuracy_metrics() -> list[GEval]:
    params = [P.INPUT, P.ACTUAL_OUTPUT]
    return [
        _geval("Falsifiable", "The claim is a specific prediction that could later be checked as true or false. Fail vague commentary, descriptions of the present, or pure opinion with no checkable outcome.", params),
        _geval("Analyst's own view", "The INPUT shows the analyst themselves making this prediction. Fail it if it is a third party's view, something the analyst only reports or quotes, or a hypothetical the analyst rejects.", params),
        _geval("Claim matches transcript", "The claim's wording matches what the transcript says: direction, price levels or numbers, and timeframe are not overstated, softened, or changed. Fail if the transcript does not support this exact prediction.", params),
        _geval("Grounds supported", "Every item listed under Grounds is actually stated or clearly shown in the transcript. Fail if any ground is invented or relies on outside knowledge not in the transcript.", params),
        _geval("Implication faithful", "'Stated implication' is either 'none', or something the analyst really told the audience to do in the transcript. Fail if it was inferred or invented. Pass when it is 'none'.", params),
        _geval("Conditions faithful", "The 'Conditions (only if)' line matches the transcript: any 'if X happens' the analyst attached to the prediction is captured, and none is invented. Pass when there are no conditions and the analyst gave none.", params),
    ]


# --- Layer 3: the analyzer's output --------------------------------------------------------


class ResolutionConsistent(BaseMetric):
    """Code check, no LLM: the analyzer's fields obey the rules in its own prompt/schema."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.async_mode = False

    @property
    def __name__(self):
        return "Resolution consistent"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        meta = test_case.additional_metadata
        r, claim = meta["resolution"], meta["claim"]
        problems = []
        if r["outcome"] == "resolved" and r["verdict"] is None:
            problems.append("outcome is resolved but verdict is null")
        if r["outcome"] != "resolved" and r["verdict"] is not None:
            problems.append(f"verdict {r['verdict']} set while outcome is {r['outcome']}")
        conditional = bool(claim.get("condition_trigger"))
        if not conditional and r["trigger_status"] is not None:
            problems.append("unconditional claim has a trigger_status")
        if conditional and r["trigger_status"] is None:
            problems.append("conditional claim has no trigger_status")
        if r["outcome"] == "trigger_expired" and (not conditional or r["trigger_status"] != "expired"):
            problems.append("trigger_expired without an expired conditional claim")
        if r["outcome"] == "resolved" and conditional and r["trigger_status"] != "triggered":
            problems.append("resolved a conditional claim whose trigger was not 'triggered'")
        if r.get("benchmark") and r["outcome"] != "resolved":
            problems.append("benchmark given for an unresolved claim")
        b = r.get("benchmark")
        if b and b.get("claim_return_pct") is not None and b.get("beat_benchmark") is not None:
            if b["beat_benchmark"] != (b["claim_return_pct"] > b["benchmark_return_pct"]):
                problems.append("beat_benchmark contradicts the two return figures")
        published = meta.get("published_at")
        if r["outcome"] == "resolved" and published:
            start = _derived_window(claim["horizon"], date.fromisoformat(published))[0]
            if start > meta["as_of"]:
                problems.append(f"resolved before its target window opens ({start} > {meta['as_of']})")
        self.score = 0.0 if problems else 1.0
        self.reason = "; ".join(problems) or "all consistency rules hold"
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success


def analyzer_metrics() -> list:
    # INPUT = claim as given to the analyzer; ACTUAL_OUTPUT = its resolution;
    # RETRIEVAL_CONTEXT = the price evidence it was given (web-search findings are not available).
    params = [P.INPUT, P.ACTUAL_OUTPUT, P.RETRIEVAL_CONTEXT]
    return [
        ResolutionConsistent(),
        _geval("Verdict supported by evidence", "Given the claim and the price evidence in RETRIEVAL_CONTEXT, the verdict (or the decision to leave it pending/expired) is justified. Check direction and, if the claim states a magnitude, that magnitude. If the rationale leans on news the price data cannot confirm, do not fail it for that alone, but fail any verdict that the price data contradicts. A flat or sideways result is not 'good' for a predicted move.", params),
        _geval("Rationale numbers match data", "Every price, date, or percentage the rationale cites agrees with the price evidence in RETRIEVAL_CONTEXT (small rounding is fine). Fail if a cited number is wrong or unsupported by the evidence. Pass if the rationale cites no price figures.", params),
        _geval("Rationale agrees with verdict", "The rationale argues for the same outcome, verdict and trigger status that are stated. Fail if the explanation points one way and the verdict the other.", params),
        _geval("Judges the claim as stated", "The analyzer judged the prediction the analyst actually made (same asset, direction, magnitude, timeframe, and conditions as in INPUT), not an easier or different one. Fail if it quietly changed the claim, e.g. judged a 20% rally by whether the price merely rose.", params),
    ]
