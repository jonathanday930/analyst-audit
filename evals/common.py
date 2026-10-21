"""Shared paths, env loading, the frozen source set, and the on-disk case cache.

Generation (expensive: claim finder + analyzer LLM calls, price fetches) and scoring (DeepEval)
are separate steps. `generate.py` writes one JSON file per source video into `cache/cases/`;
the tests read those files, so re-scoring or tweaking a metric never re-runs the pipeline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

EVALS = Path(__file__).resolve().parent
BACKEND = EVALS.parent / "backend"
CASES_DIR = EVALS / "cache" / "cases"
SHORTSET_DIR = BACKEND / "scripts" / "output" / "shortset_claims"

# Keys live in backend/.env; load them into the process so app.config picks them up no matter
# where we run from. No data goes to Confident AI (DeepEval's hosted dashboard).
load_dotenv(BACKEND / ".env")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_RESULTS_FOLDER", str(EVALS / "cache" / "results"))


def load_shortset() -> list[dict]:
    """The 10 frozen videos: manifest fields, frozen claim-finder claims, cached transcript."""
    from app.youtube import transcript_cache

    rows = []
    for entry in json.loads((SHORTSET_DIR / "manifest.json").read_text()):
        frozen = json.loads((BACKEND / entry["claims_file"]).read_text())
        transcript = transcript_cache.read(entry["video_id"])
        if not transcript:
            raise RuntimeError(f"No cached transcript for {entry['video_id']}; never bulk-refetch (see testing/README.md).")
        rows.append({**entry, "transcript": transcript, "frozen_claims": frozen["claims"]})
    return rows


def load_cases() -> list[dict]:
    """One dict per (video, claim) from the cache, flattened for pytest parametrization."""
    cases = []
    for path in sorted(CASES_DIR.glob("*.json")):
        video = json.loads(path.read_text())
        for item in video["claims"]:
            cases.append({"video": video, **item})
    return cases


def case_id(case: dict) -> str:
    return f"{case['video']['channel']}-{case['video']['video_id']}-claim{case['index']}"
