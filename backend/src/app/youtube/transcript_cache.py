"""On-disk cache for fetched transcript text, keyed by video id.

Re-fetching the same video's transcript from YouTube every time is wasted network traffic that
was never necessary — the transcript for a given video id never changes — and it's exactly the
kind of avoidable repeat traffic that contributes to a rate-limit ban (see rate_limit.py and
testing/README.md). Prompt-tuning workflows (promptlab, preview_batch.py) especially re-run the
same handful of test videos over and over, so this also just makes iteration faster.

Plain text files, not a database: this is a local dev cache, not application state — safe to
delete the whole directory at any time, and it's gitignored (backend/.cache/)."""

from pathlib import Path

_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "transcripts"


def read(video_id: str) -> str | None:
    path = _CACHE_DIR / f"{video_id}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else None


def write(video_id: str, text: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (_CACHE_DIR / f"{video_id}.txt").write_text(text, encoding="utf-8")
