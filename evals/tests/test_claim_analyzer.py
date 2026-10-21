"""Layer 3: the claim analyzer's output for each claim, scored on its own."""

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from common import case_id, load_cases
from formatting import analyzer_input_text, resolution_text
from metrics import analyzer_metrics

CASES = [c for c in load_cases() if c.get("analysis")]


@pytest.mark.skipif(not CASES, reason="no analyzed cases: run evals/generate.py first")
@pytest.mark.parametrize("case", CASES, ids=[case_id(c) for c in CASES])
def test_analyzer_output_is_sound(case):
    analysis = case["analysis"]
    if "error" in analysis:
        pytest.fail(f"analyzer crashed during generation: {analysis['error']}")
    video = case["video"]
    test_case = LLMTestCase(
        input=analyzer_input_text(case["claim"], video["published_at"], analysis["as_of"]),
        actual_output=resolution_text(analysis["resolution"]),
        retrieval_context=analysis["evidence"],
        additional_metadata={
            "resolution": analysis["resolution"], "claim": case["claim"],
            "published_at": video["published_at"], "as_of": analysis["as_of"],
        },
    )
    assert_test(test_case, analyzer_metrics())
