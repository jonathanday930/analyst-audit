"""Export cached claims as a blank human-labeling CSV.

This deliberately does not invoke DeepEval or any model.  The resulting file is a small,
stable annotation sheet that can be filled in by a human before ``calibrate.py`` is run.
"""

from __future__ import annotations

import csv
from pathlib import Path

from common import CASES_DIR, load_cases


LABEL_COLUMNS = (
    "falsifiable",
    "analyst_own_view",
    "claim_matches_transcript",
    "grounds_supported",
    "implication_faithful",
    "conditions_faithful",
)
OUTPUT = Path(__file__).resolve().parent / "labels" / "claim_labels.csv"


def export_labels(output: Path = OUTPUT) -> int:
    """Write one blank-label row per cached claim and return the row count."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["video_id", "claim_index", "claim_text", *LABEL_COLUMNS]
    cases = load_cases()
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            claim = case["claim"]
            writer.writerow({
                "video_id": case["video"]["video_id"],
                "claim_index": case["index"],
                "claim_text": claim.get("claim", ""),
                **{column: "" for column in LABEL_COLUMNS},
            })
    return len(cases)


def main() -> int:
    count = export_labels()
    print(f"Exported {count} claims to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
