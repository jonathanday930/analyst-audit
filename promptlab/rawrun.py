"""Raw mode: run a pass as a plain Claude call and keep exactly what came back.

The pipeline's passes normally go through `parse_structured`, which pins the answer to a
pydantic schema in `app/llm/schemas.py`. That is right in production and actively misleading
while a prompt is being redesigned: ask for a different set of fields and the structured-output
call still returns the old ones, so the prompt looks like it did nothing. Raw mode drops the
`output_format` entirely, so what the lab displays is what the model wrote.

The system prompt comes from the editor; the user turn comes from the pass's own
`build_user_content`, so a prompt tuned here is tuned against the same input production sends.

Claim analyzer is not available here: its user turn is built from one already-extracted claim
(`ClaimContext`), which raw mode has no way to produce. It stays a pipeline-mode pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import bootstrap  # noqa: F401  -- sys.path/env setup; must import before app.*

from app.llm import claim_finder, stance_extractor
from app.llm.client import RawCompletion, complete_text
from app.sources.fetcher import FetchedSource

# Thinking mirrors each pass's production setting (see the modules' docstrings): claim finder
# reasons about the source, the stance extractor is a mechanical pull. Token ceilings match too,
# except that raw answers are prose rather than a compact object, so they get more headroom.
RAW_PASSES = {
    "claim_finder": {"thinking": True, "max_tokens": 24000},
    "stance_extractor": {"thinking": False, "max_tokens": 8000},
}


@dataclass
class RawPassResult:
    pass_id: str
    model: str
    system_prompt: str
    user_content_preview: str
    completion: RawCompletion | None
    error: str | None = None


def _user_content(pass_id: str, source: FetchedSource, today: date) -> str:
    if pass_id == "claim_finder":
        return claim_finder.build_user_content(
            title=source.title,
            published_at=source.published_at,
            fetched_at=today,
            source_text=source.content,
        )
    return stance_extractor.build_user_content(source_text=source.content)


def run_raw_pass(
    *, pass_id: str, system_prompt: str, model: str, source: FetchedSource, today: date
) -> RawPassResult:
    settings = RAW_PASSES[pass_id]
    user_content = _user_content(pass_id, source, today)
    # The transcript is most of the user turn and is already saved as source.txt; the preview
    # keeps the run record honest about what was sent without duplicating all of it.
    preview = user_content[:400] + ("..." if len(user_content) > 400 else "")
    try:
        completion = complete_text(
            model=model,
            system=system_prompt,
            user_content=user_content,
            max_tokens=settings["max_tokens"],
            thinking=settings["thinking"],
        )
    except Exception as exc:  # noqa: BLE001 -- one failed pass shouldn't lose the others
        return RawPassResult(pass_id, model, system_prompt, preview, None, f"{type(exc).__name__}: {exc}")
    return RawPassResult(pass_id, model, system_prompt, preview, completion)
