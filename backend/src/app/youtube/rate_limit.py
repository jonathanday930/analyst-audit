"""Cross-process serialization for outbound YouTube requests.

A burst of concurrent transcript/metadata fetches — not steady sequential traffic — is what
triggers YouTube's `IpBlocked`/`RequestBlocked` exceptions (confirmed the hard way: a batch of
10 parallel `fetch_source` calls got this machine's IP banned for the better part of a day). This
module makes that burst structurally impossible rather than relying on every caller to remember
not to do it: `throttle()` holds an exclusive file lock for the duration of any wait it imposes,
so concurrent callers — separate processes included, e.g. several `run_claimfinder_only.py`
invocations launched at once — queue up on the lock and drain out one at a time, each spaced at
least `Settings.youtube_min_request_interval_seconds` apart. See testing/README.md's "Never fetch
YouTube sources in parallel" for the incident this exists to prevent.
"""

import fcntl
import time
from pathlib import Path

from app.config import get_settings

# backend/.cache/ — gitignored, ephemeral, safe to delete any time.
_LOCK_PATH = Path(__file__).resolve().parents[3] / ".cache" / "youtube_rate_limit.lock"


def throttle() -> None:
    """Block until at least `youtube_min_request_interval_seconds` has elapsed since the last
    call to this function from ANY process on this machine, then record this call's timestamp.
    Call this immediately before every outbound YouTube request (transcript fetch, metadata
    fetch, yt-dlp fallback) — never skip it "just this once", that's exactly how the original
    ban happened."""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LOCK_PATH.touch(exist_ok=True)
    min_interval = get_settings().youtube_min_request_interval_seconds

    with open(_LOCK_PATH, "r+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            raw = lock_file.read().strip()
            last_ts = float(raw) if raw else None
            now = time.time()
            if last_ts is not None:
                wait = min_interval - (now - last_ts)
                if wait > 0:
                    time.sleep(wait)
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(str(time.time()))
            lock_file.flush()
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
