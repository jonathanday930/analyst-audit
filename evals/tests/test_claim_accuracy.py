"""Layer 1: each claim the claim finder produced, scored on its own against its transcript."""

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from common import case_id, load_cases
from formatting import claim_text, source_text
from metrics import claim_accuracy_metrics

CASES = load_cases()


@pytest.mark.skipif(not CASES, reason="no cases: run evals/generate.py first")
@pytest.mark.parametrize("case", CASES, ids=[case_id(c) for c in CASES])
def test_claim_is_accurate_to_transcript(case):
    test_case = LLMTestCase(input=source_text(case["video"]), actual_output=claim_text(case["claim"]))
    assert_test(test_case, claim_accuracy_metrics())
