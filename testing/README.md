# Testing notes

Practices and known gotchas for running the pipeline against real sources during development —
distinct from `analyst-test-set.md` (which videos to use), this file is about how to run them
without breaking the tooling for yourself or the next session.

## Never fetch YouTube sources in parallel

**What happened:** a batch run of 10 videos was kicked off as 10 separate concurrent processes
(each calling `fetch_source` -> `fetch_metadata`/`fetch_transcript` at the same moment). YouTube
responded by IP-blocking this machine's network (`youtube_transcript_api.IpBlocked`) for the
better part of a day. Every subsequent fetch attempt failed the same way — including calls made
hours later, retried with backoff, and even calls routed through a proxy's free/shared IP tier
(which turned out to already be flagged by Google's own anti-bot check, a different but equally
dead end).

**Why it happened:** YouTube's blocking is triggered by *burst* traffic, not steady sequential
traffic — the library's own docs are explicit about this ("YouTube has started blocking most IPs
that are known to belong to cloud providers... Same can happen to the IP of your self-hosted
solution, if you are doing too many requests"). Ten requests landing in the same second reads as
a scraper; ten requests spread out over a couple of minutes does not. The production app's own
design only ever issues one fetch at a time anyway (see `../CLAUDE.md`'s "Onboarding a new
analyst" — every claim is seeded by pasting one link), so this was purely a test-tooling mistake,
not a real usage pattern.

**What's now in place so this can't happen again**, all in `backend/src/app/youtube/`:

- **`rate_limit.py`** — `throttle()` is called at the top of every outbound YouTube request
  (`fetch_transcript`, `fetch_metadata`, and the yt-dlp fallback below). It enforces a minimum
  spacing (`Settings.youtube_min_request_interval_seconds`, default 5s) between *any* two such
  requests **across processes**, using an exclusive file lock (`backend/.cache/*.lock`) — so even
  several scripts launched at once queue up and drain out one at a time instead of bursting.
  Don't add a new YouTube-hitting call path without calling `throttle()` first.
- **`transcript_cache.py`** — every successfully fetched transcript is cached to
  `backend/.cache/transcripts/<video_id>.txt` and read from there first. Re-running claim finder
  against the same test video (very common while tuning prompts) never re-hits YouTube at all
  after the first fetch. Safe to delete the whole `backend/.cache/` directory any time — it's
  gitignored and purely a local dev convenience, not application state.
- **`transcript.py`'s yt-dlp fallback** — if the primary `youtube_transcript_api` path fails for
  any reason other than a permanent fact about the video (captions disabled, video unavailable),
  it retries via yt-dlp's own caption download, a different request shape that doesn't always
  trip the same block at the same moment even from the same IP. Still hits YouTube directly
  though, so a genuine IP-wide ban (see below) takes this one down too.
- **`transcript.py`'s Supadata fallback** — if yt-dlp also fails, it retries once more via
  [supadata.ai](https://supadata.ai)'s hosted transcript API (`Settings.supadata_api_key` /
  `SUPADATA_API_KEY`). This is the one that actually matters for a real IP ban: Supadata fetches
  the transcript from YouTube on *its own* infrastructure, not this machine's, so our IP being
  blocked is irrelevant to it. Confirmed working: this is what actually unblocked testing after
  both the primary path and yt-dlp were still failing on a live, confirmed-active ban (see the
  incident above). Free-tier limits apply; unset the key to skip this fallback entirely.

**A fourth fallback (`_fetch_via_easytranscriber`, `EASYTRANSCRIBER_API_KEY`) exists in
`transcript.py` but is unverified** — added without a real API key configured or a confirmed
working request/response shape, unlike Supadata above. It's inert as long as
`EASYTRANSCRIBER_API_KEY` stays unset. Verify it actually works (real key, one successful fetch)
before relying on it, the same way Supadata was verified here.

**If you still get blocked despite all of this** (a shared network, someone else's traffic, bad
luck, or all fallbacks including Supadata failing): don't loop retries from the same process —
that's the same mistake in miniature. Either wait it out, fetch from a different network you
already have access to, or paste the transcript text manually and call `extract_claims` directly
with it (skips the network fetch entirely). Webshare's *paid* residential proxy tier is the other
thing that reliably gets around a genuine IP ban per the library's own docs, but that costs money
— Supadata's free tier covers normal single-video testing without it.

## Running the short test set

Never invoke `run_claimfinder_only.py` (or `preview_pipeline.py`) more than one at a time via
separate background processes — that's exactly the mistake above. `preview_batch.py` already
runs its URLs sequentially in one process for this reason; prefer it over hand-rolling a batch
of parallel one-off calls.
