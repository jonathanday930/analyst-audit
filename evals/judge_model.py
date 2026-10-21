"""DeepEval judge backed by the app's own Anthropic client, so evals use the same key/config.

Override the judge with EVAL_JUDGE_MODEL. Judging Claude output with Claude is biased toward
agreement, so keep the judge model pinned and independent of whichever pass model is being
tested (e.g. don't let a swapped-in open-weight model also judge itself).
"""

from __future__ import annotations

import json
import os

from deepeval.models import DeepEvalBaseLLM
from pydantic import BaseModel

import common  # noqa: F401  (loads backend/.env before app.config is read)
from app.config import get_settings
from app.llm.client import complete_text, parse_structured

DEFAULT_JUDGE_MODEL = "claude-sonnet-5"


class AnthropicJudge(DeepEvalBaseLLM):
    def __init__(self, model: str | None = None):
        self._model_id = model or os.environ.get("EVAL_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL
        super().__init__(self._model_id)

    def load_model(self):
        get_settings()  # fail early if the key/config is missing
        return self

    def generate(self, prompt: str, schema: type[BaseModel] | None = None):
        if schema is None:
            return complete_text(model=self._model_id, system="You are a careful, strict evaluator.", user_content=prompt, max_tokens=4000, thinking=False).text
        try:
            return parse_structured(model=self._model_id, system="You are a careful, strict evaluator.", user_content=prompt, schema=schema, max_tokens=4000)
        except Exception:  # noqa: BLE001 -- schema not supported by structured output; fall back to JSON text
            text = complete_text(model=self._model_id, system="Reply with JSON only.", user_content=prompt, max_tokens=4000, thinking=False).text
            return schema.model_validate(json.loads(text[text.index("{") : text.rindex("}") + 1]))

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self._model_id


_judge: AnthropicJudge | None = None


def get_judge() -> AnthropicJudge:
    global _judge
    if _judge is None:
        _judge = AnthropicJudge()
    return _judge
