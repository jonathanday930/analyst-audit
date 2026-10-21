#!/usr/bin/env python3
"""Run claim analyzer only against already-extracted claims, so the analyzer prompt can be
iterated on without re-running claim finder each time — a fresh claim-finder call costs time and
tokens and can shuffle the claims themselves (the pass isn't deterministic), which defeats
holding the input fixed while tuning the analyzer. Companion to run_claimfinder_only.py: feed it
that script's --out file as input here.

Reuses preview_pipeline._check_claim (ticker resolution, price/benchmark fetch, resolve_claim)
so this never drifts from the real per-claim resolution path — see app/llm/claim_analyzer.py and
the Claim analyzer stage description in CLAUDE.md.

Usage:
    python scripts/run_claimanalyzer_only.py claims.json --out resolutions.json
    python scripts/run_claimanalyzer_only.py claims.json --out resolutions.json --prompt-file draft_prompt.txt

claims.json is a run_claimfinder_only.py --out file (has "claims" and "published_at").
--prompt-file, if given, replaces CLAIM_ANALYZER_SYSTEM_PROMPT for this run only — the checked-in
prompt in app/llm/claim_analyzer.py is never touched by this script.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

from app.llm.schemas import ClaimExtraction
from preview_pipeline import PromptOverrides, _check_claim


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("claims_file", help="Output file from run_claimfinder_only.py")
    parser.add_argument("--prompt-file", default=None, help="System prompt override for this run")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    claims_data = json.loads(Path(args.claims_file).read_text(encoding="utf-8"))
    published_at = (
        date.fromisoformat(claims_data["published_at"]) if claims_data.get("published_at") else None
    )
    today = datetime.now(timezone.utc).date()

    prompt_override = (
        Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else None
    )
    overrides = PromptOverrides(claim_analyzer_system=prompt_override)

    results = []
    for raw in claims_data["claims"]:
        claim = ClaimExtraction.model_validate(raw)
        try:
            checked = _check_claim(claim, published_at=published_at, today=today, overrides=overrides)
            resolution = checked.resolution
            results.append(
                {
                    "asset_description": claim.asset_description,
                    "suggested_ticker": claim.suggested_ticker,
                    "claim": claim.claim,
                    "horizon": claim.horizon,
                    "condition_trigger": claim.condition_trigger,
                    "benchmark_ticker": checked.benchmark_ticker,
                    "used_web_search": checked.used_web_search,
                    "resolution": resolution.model_dump() if resolution else None,
                    "error": None,
                }
            )
            status = f"{resolution.outcome}" + (f"/{resolution.verdict}" if resolution.verdict else "")
            print(f"  {claim.asset_description}: {status}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 -- surfaced in the JSON, not raised
            results.append(
                {
                    "asset_description": claim.asset_description,
                    "claim": claim.claim,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }
            )
            print(f"  {claim.asset_description}: ERROR {exc}", file=sys.stderr)

    out = {
        "source_claims_file": args.claims_file,
        "prompt_file": args.prompt_file,
        "published_at": claims_data.get("published_at"),
        "today": today.isoformat(),
        "results": results,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"-> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
