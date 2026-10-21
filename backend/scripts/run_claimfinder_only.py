#!/usr/bin/env python3
"""Run claim finder only (no claim analyzer, no evaluation) against one URL and dump the raw
ClaimExtraction schema output as JSON. Built for a one-off batch review across several sources
run concurrently as separate OS processes — see scripts/README or the analyst-audit CLAUDE.md
for the pipeline this pulls from (app/llm/claim_finder.py's extract_claims).

Usage:
    python scripts/run_claimfinder_only.py <url> --channel "Name" --out out.json
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone

from app.llm.claim_finder import extract_claims
from app.sources.fetcher import SourceFetchError, fetch_source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--channel", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    result = {
        "channel": args.channel,
        "url": args.url,
        "status": "error",
        "error": None,
        "source_title": None,
        "published_at": None,
        "claims": [],
    }
    try:
        source = fetch_source(args.url)
        result["source_title"] = source.title
        result["published_at"] = source.published_at.isoformat() if source.published_at else None

        claim_result = extract_claims(
            title=source.title,
            published_at=source.published_at,
            fetched_at=today,
            source_text=source.content,
        )
        result["claims"] = [c.model_dump() for c in claim_result.claims]
        result["status"] = "ok"
    except SourceFetchError as exc:
        result["error"] = f"source fetch failed: {exc}"
    except Exception as exc:  # noqa: BLE001 -- surfaced in the JSON for the batch runner, not raised
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"{args.channel}: {result['status']} ({len(result['claims'])} claims) -> {args.out}", file=sys.stderr)
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
