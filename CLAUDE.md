# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## What this is

A track-record system for finance "analysts" (YouTube channels, blogs — Twitter/X explicitly out
of scope for now). It extracts every falsifiable claim a analyst makes from their long-form
content, checks over time whether each one panned out, and rolls that up into a per-analyst
reliability score. The eventual goal is to compile scores across several analysts to help judge
whether a current buy/sell idea is worth acting on — but that final synthesis step is deferred
(see MVP scope below).

This is a sibling project to `../youtube_fact_checker`, which does single-video "would
following this video's advice have paid off" analysis. `AnalystAudit` is a different product,
not an evolution of it — it's stateful (persistent claim history per analyst) where the other is
deliberately stateless, and its claim schema is intentionally *not* a trade-action framing (see
Claim schema below). Reusable infrastructure — the Claude structured-output client pattern,
ticker resolution, yfinance price fetching, YouTube transcript/metadata fetching — should be
ported over from `youtube_fact_checker`'s backend rather than rebuilt from scratch; the
extraction/evaluation prompts and schemas should not be reused as-is.

## Architecture: three pipeline stages

1. **Claim finder** — extracts claims from one source (a video transcript or blog post),
   deliberately does NOT categorize by asset class/topic, does NOT collapse multiple scenarios
   in one video into a single "base case" (each distinct condition+outcome pair is recorded as
   its own claim, even if two claims from the same analyst/video would look contradictory), and
   does NOT translate into a long/short/avoid trade-action framing. Source-agnostic: the prompt
   and schema don't care whether the text came from a transcript or a blog post — only the
   text-extraction step differs per source type (YouTube transcript API vs. fetching a blog URL
   and pulling the article body out of the page).
2. **Claim analyzer** — a recurring/scheduled job (not one-shot like `youtube_fact_checker`'s
   evaluation pass) that rechecks open claims as their target windows arrive and resolves each
   to a verdict. Must handle conditions that are price levels (checkable via price data) AND
   real-world events (e.g. "Iran reaches a ceasefire" — checkable only via web search/news, the
   same fallback `youtube_fact_checker`'s evaluation pass already uses). Claims with no target
   window at all (open-ended "long-term bullish" stances) need periodic re-checks rather than a
   single resolve-once check.
3. **Meta analyst analysis** — reads a analyst's whole claim history (raw claims + resolved verdicts)
   and derives categorization/scoring after the fact (e.g. "good at crypto, bad at macro calls")
   — categorization is deliberately NOT baked in at claim-finder time, so the categorization
   scheme can change later without needing to re-extract anything.

A fourth stage — combining several trusted analysts' currently-open claims into a "does this
buy/sell make sense right now" read — was discussed and explicitly deferred. Once 1-3 exist,
it's expected to be a prompt over existing data, not new infrastructure.

### Stance/sentiment extractor (runs alongside claim finder)

A separate AI step, run over the same source text as claim finder (same source-agnostic
text-extraction step feeds both), pulls out fuzzier context that isn't a falsifiable claim:
positions an analyst says they've personally taken, and general market-sentiment reads. This is
deliberately a second prompt, not a second responsibility bolted onto claim finder, because the
two jobs need different rigor — claim finder is strict (condition/outcome/window, precise
by design), stance extraction is loose on purpose. It produces no condition/outcome/window, so
it never enters claim analyzer's resolve loop and is never marked good/bad — it exists purely as
supporting context for stage 3 (meta-analyst analysis), e.g. explaining that an analyst who kept
calling for a crash while personally staying long tech says something different about their
reliability than one who was calling and positioned the same way.

## Stance schema (what the stance/sentiment extractor produces)

Per stance record: analyst id + source metadata (same fields as claims: source type, source
url/id, published date), timestamp, and one of:
- a **position** — ticker/instrument + direction (long / short / exited) + the analyst's own
  wording, for when they disclose a trade or holding of their own.
- a **sentiment read** — freeform quote + a coarse bucket (bullish / neutral / bearish /
  uncertain) for the market broadly or a sector, for general "how are they feeling" commentary
  that isn't tied to one instrument.

No target window, no trigger lifecycle, no verdict — stances are never resolved and never scored
individually. Whether/how meta-analyst analysis weights them is a stage-3 concern, not something
decided at extraction time (same "don't bake in scoring logic early" principle as claim
categorization, see stage 3 above).

### Stance market snapshot (deterministic, non-LLM)

Separately from the above, `app/prices/stance_snapshot.py` computes real price stats for a
stance's resolved ticker directly from `yfinance` history — no LLM call, no verdict. Given a
stance and the date it was made (the source's `published_at`), it reports: current price, the
high and low the ticker has hit since the call (with their dates), the simple % change from the
call-date price to now, and days elapsed. This is what backs "if an analyst says 'I have a
position in gold,' or 'the economy will do better,' show me what gold / the S&P 500 has actually
done since" — real numbers, at effectively zero cost, without touching claim analyzer's LLM +
web-search path.

This does **not** turn a stance into a scored claim — it's descriptive stats only, computed fresh
on every read rather than stored (a "high since call" value is only valid as of when it's
computed), and it does not decide good/bad. It's meant to sit alongside a stance for a human
reader, and eventually as an additional, deterministic input to meta-analyst analysis (stage 3) —
same "stances are never resolved individually" principle as above, just with real numbers attached
instead of none.

`resolve_stance_ticker()` reuses claim finder's ticker-resolution path (`ticker_resolver.py`):
positions match on `asset_description` the same way claims do; broad sentiment reads (no specific
instrument, just a `scope` like "the economy" or "the market") are resolved the same way by
matching `scope` text instead — `ticker_resolver.py`'s alias table now includes "the economy" →
SPY alongside its existing S&P 500/Nasdaq/crypto/commodity aliases, so "the economy will do
better" resolves to a benchmark index the same deterministic way "I'm long gold" resolves to
`GC=F`. A stance with no resolvable ticker (too vague, e.g. "feeling constructive on risk assets")
just gets no snapshot — that's expected, not an error.

Wired into the preview tooling today (`compute_stance_snapshot`/`resolve_stance_ticker` called
from `preview_pipeline.py`'s `_check_stance`, shown on every stance card in all three preview
scripts) since the real `stances` table/API don't exist yet — see Status below and `TASKS.md`.

`ticker_resolver.py` always checks `suggested_ticker` before the alias table, never the other
way around — the model's own guess about the specific instrument(s) actually named beats a
generic phrase match every time (a claim about "gold mining stocks" must not resolve to gold
the commodity just because "gold" appears in its `asset_description`). Claim resolution
(`resolve_tickers()`, used by `preview_pipeline.py`'s `_check_claim`) can return more than one
ticker when a claim names several instruments — a basket ("the Magnificent 7" -> seven tickers)
or a relative comparison ("QQQ relative to SCHD" -> both) — and `claim_analyzer.py`'s
`resolve_claim()` takes `price_series` as a list for exactly this reason, feeding every named
instrument's price history to the model so it judges the basket/comparison as a whole rather
than picking one arbitrary member. Stances stay single-ticker (`resolve_ticker()`, the first
result of `resolve_tickers()`) since a stance is always about one instrument or one broad scope.

### Onboarding a new analyst: one step, link-only — no separate channel/feed tracking setup

There is no separate "Add analyst" registration flow, and no automatic channel/feed tracking for
MVP — the UI has one universal entry point, "Add a link": paste any single video or blog post
URL, and it tries to match the source against analysts already on file (via `detectExpert`/
`detectSourceType` in the mockup — a placeholder substring match; the real algorithm needs to
match on the pasted link's actual channel ID / blog domain against sources seen on prior claims
for that analyst, not guess from the URL's text). If it matches, the claim(s) get attached to that
analyst's existing history. If it doesn't match, the flow asks for **just a name**, creates a analyst
profile for them automatically, and attaches the claim(s) to it — a single paste-and-go action,
one screen, no second step.

There is deliberately no channel/feed-URL step, no "keep this analyst tracked automatically" prompt,
and nothing to skip. Every claim, for every analyst, is seeded by someone manually pasting a video
or blog link — the claim finder never polls a channel or feed on its own for MVP (see MVP scope
below). Adding another post/video to a analyst you already track (via that analyst's own profile page)
just asks for the one video/post URL, same as the new-analyst path minus the name prompt.

### Evaluation includes a benchmark comparison

When claim analyzer resolves a claim, its evaluation should include not just the verdict but
whether the trade beat a relevant benchmark over the same window (S&P 500 / Nasdaq for
equity-ish claims, a major cryptocurrency for crypto claims) — a call can be a "good call" in
isolation but still have been worse than just holding an index fund, and that's a distinct,
useful signal from the raw verdict. Not every claim needs this (e.g. a rates/yield claim isn't
naturally expressed as a comparable return), so it's an optional part of the evaluation, not a
required field.

## Claim schema (what claim finder produces)

Per claim: asset/instrument description + one or more best-guess tickers (kept as plain best
guesses, same role as `suggestedTicker` in `youtube_fact_checker` — final resolution to a real
tradeable symbol still happens in a separate deterministic step, not at extraction time), condition/
trigger (freeform text — a price level OR a real-world event, not necessarily numeric), the raw
claim/predicted outcome, and horizon (short-term/swing vs. long-term/structural — captured as a
raw fact from the analyst's own wording, not a judgment call). The extraction also requires
source-based grounds and the reasoning warrant connecting those grounds to the claim. It may
include backing, the analyst's stated implication, qualifier, confidence, and rebuttal/
invalidation context. Confidence is a 1-99 proxy for the analyst's expressed confidence, not the
model's belief. Concrete resolution dates are not claim-finder output; downstream analysis derives
rough timing from the horizon and publication date. Source metadata (analyst id, source type,
source url/id, published date) is attached in code, not part of the model's reasoning.

Conditional claims (an "if X happens" trigger) need a downstream staleness deadline for how long
the condition itself stays live before the claim goes stale. A claim whose trigger deadline passes
with the condition never firing resolves to a distinct **expired** state — moot, not folded into
good/bad. The extractor records the condition itself; it does not invent a condition timeframe.

## MVP scope

- Sources: video transcripts and blog posts only. Twitter/X is explicitly out — tweets are
  often too short or thread-dependent to contain a full claim on their own, not worth the
  thread-assembly work for a first version.
- Trading horizon focus: swing trades and longer-term plays, not short-term/day-trading
  "gambling" calls. Concretely, the user's own frame of reference is something like a 10% gain
  over a ~4-month holding period — "short-term" for this app's horizon field should mean
  "days to a few weeks" (deprioritized), and "swing/long-term" should mean "roughly 1 to
  12+ months" (the zone that matters here), not the more typical trading-world short/long split.
- No auth/OAuth, no payment plans, no multi-user support yet — single-user (the owner) for now.
  Planned for later, not designed for yet.
- Orchestration: plain scheduled jobs in the backend (cron / Fly.io scheduled machines), not
  a workflow tool like n8n — the actual logic (typed schemas, structured-output parsing,
  per-claim error handling) fits better as backend code than as workflow-tool nodes. n8n could
  be revisited later purely for source-polling triggers (e.g. watching a YouTube channel or
  blog RSS feed for new content) if that becomes painful to hand-roll — not needed for MVP.
- No automatic channel/feed tracking: every claim is seeded by manually pasting a video or blog
  link (see onboarding above). The app never polls or watches a analyst's channel/feed for new
  content on its own for MVP.

## Frontend and data model notes (for building the real app)

The UI/UX is fully designed and approved — implement it, don't redesign it. The canonical
reference is `design/mockup/prototype/index.html`, a real clickable prototype (plain HTML/CSS/
vanilla JS, opens in any browser, no login or build step) covering all 5 screens: Watchlist,
Browse all, Expert profile, Claim detail, and the Add-link flow (a single-step onboarding — paste
a link, detect or name the analyst, done, per the one-step description above). Read
`design/README.md` first for how to use it and what's superseded;
`design/mockup/Main.dc.html` is the original source in Claude Design's own templating format —
don't open it directly in a browser, it won't render (see that README for why).

Match the prototype's design tokens exactly rather than re-deriving them: the CSS custom
properties at the top of `prototype/index.html` (`--bg`, `--card`, `--accent`, `--good`, `--bad`,
etc.) are the actual approved dark "trading terminal" palette, plus Space Grotesk (UI text) and
JetBrains Mono (data/numbers/tickers) from Google Fonts.

Everything in the prototype is hardcoded fixture data with no persistence —
`getAnalysts()`/`getClaims()`/`getDraftClaims()` show the shape of the real data, but a few fields
are display-only strings in the mockup; the real schema currently uses horizon-derived timing and
does not expose the mockup's stated-timeframe or target-window strings as extraction fields.
Conditional claims use trigger lifecycle fields:
  `trigger_status` (waiting / triggered / expired),
  `trigger_observed_at`, and a computed `trigger_deadline` (from the analyst's stated condition
  timeframe when available downstream, or the default staleness period if none was stated). `status` needs a third value,
  `expired`, alongside `open`/`resolved`, for claims whose trigger deadline passed unmet.
- `status` (open/resolved/expired) and `verdict` (good/bad, set only once resolved) are separate
  fields — don't conflate into one enum.
- `benchmarks` is optional per claim, only present when there's a comparable return (per
  "Evaluation includes a benchmark comparison" above) — not every claim needs one.
- The mockup's `detectExpert()` (URL-substring matching against a analyst's name/id) is a UI
  placeholder, not the real matching algorithm — the real version needs to match the pasted
  link's actual channel ID / blog domain against the sources already on file for that analyst's past
  claims, not guess from the URL's text (there's no separately stored channel/feed URL to match
  against — see onboarding above).

This is a genuinely persistent app — unlike `../youtube_fact_checker` (its sibling, deliberately
stateless), claim history has to survive across the claim analyzer's recurring re-checks, so a
real database is required, not an in-memory/session store. Reuse the Claude structured-output
client pattern, ticker resolution, yfinance price fetching, and YouTube transcript/metadata
fetching from `youtube_fact_checker`'s backend per "What this is" above — don't rebuild those
from scratch.

### Division of labor

General rule across all projects here (see root `AGENTS.md`): Claude handles major/architectural
decisions, Codex handles grunt work, CRUD, QA, and second opinions. For this project
specifically, that split means: Codex is building the frontend and the database/persistence
layer (real schema, CRUD, the screens above wired to real data). The claim finder / stance
extractor / claim analyzer / meta analyst analysis prompts, the actual AI extraction and
evaluation logic, are being handled separately, iteratively, elsewhere. Codex's backend work
should leave clean seams (API endpoints, job hooks) for those to plug into rather than building
throwaway stand-ins for them, but shouldn't attempt to implement the extraction/evaluation
prompts itself.

### Model choice

All four passes (`backend/src/app/llm/claim_finder.py`, `stance_extractor.py`,
`claim_analyzer.py`, `meta_analyst.py`) default to `claude-sonnet-5` for now, deliberately: the
plan is to use Claude as the quality benchmark first, then swap in and tune cheaper open-weight
models pass by pass once each one's output is validated against that benchmark — not a
Haiku-first design like `../youtube_fact_checker`'s two passes started as. Each pass's model is
a separate config setting (`app/config.py`) specifically so they can be swapped independently as
that validation happens. `stance_extractor` runs with thinking off and no tools (a comparatively
mechanical pull); the other three use adaptive thinking, and `claim_analyzer` also gets web
search, for the same reasons `youtube_fact_checker`'s extraction/evaluation passes needed
thinking (see that project's CLAUDE.md's own Model choice section) — don't downgrade any pass
off Sonnet without re-validating its output first.

### LLM provider status and Hugging Face migration

The model settings are provider-agnostic in name only; the current implementation is still
Anthropic-specific. `backend/src/app/llm/client.py` constructs an Anthropic client and uses
Anthropic structured parsing, adaptive-thinking fields, response-block parsing, and the
Anthropic web-search tool. Changing a `*_MODEL` setting to a Hugging Face model ID therefore
does not work by itself.

Hugging Face is the planned provider for the open-weight passes. The intended integration is its
OpenAI-compatible Inference Providers endpoint (`https://router.huggingface.co/v1`), using a
Hugging Face token and JSON-schema structured output generated from the existing Pydantic models.
The client should be split behind a provider-neutral interface so the extraction modules and
schemas do not change when the provider changes. This should support both hosted Hugging Face
Inference Providers and, later, a self-hosted Hugging Face model served through an
OpenAI-compatible server such as vLLM.

The claim finder is the easiest first migration because it does not use tools. Initial candidates
are `openai/gpt-oss-20b` and `Qwen/Qwen3-32B`; both must be evaluated against the Claude baseline
for missed claims, collapsed scenarios, third-party attribution, invented implications, and
malformed or incomplete fields.

The claim analyzer is not fully portable yet: its web search currently comes from Anthropic and
must either remain on Anthropic or receive a separate search implementation before moving that
pass to Hugging Face. `HUGGINGFACE_API_KEY` exists in `backend/.env.example` as a placeholder,
but Hugging Face is not wired into `app/config.py` or the LLM client yet.

## Status

UI/UX design is done (see prototype above). Backend and frontend scaffolding, the DB schema/CRUD,
the real matching algorithm, all 5 screens wired to real endpoints, and the ported infra
(LLM client, ticker resolver, price data, YouTube transcript/metadata, blog fetcher) are done —
see `TASKS.md` for the line-by-line record. YouTube transcript/metadata fetching is
rate-limited, cached, and falls back to yt-dlp on failure (`backend/src/app/youtube/`) — see
`testing/README.md`'s "Never fetch YouTube sources in parallel" before writing any script that
fetches more than one source, or a batch run WILL get this machine IP-blocked by YouTube for a
long time. Postgres has not been provisioned on Fly.io yet
(billable infra action, needs explicit go-ahead). The claim-finder/stance-extractor/
claim-analyzer/meta-analyst prompts — the actual AI extraction and evaluation logic, per "Model
choice" above — are written (`backend/src/app/llm/`) but not yet wired into the job seams; that
wiring, plus the `stances` table itself (schema per "Stance schema" above), are still open — see
`TASKS.md`. The deterministic stance market snapshot (`app/prices/stance_snapshot.py`, per
"Stance market snapshot" above) is done and covered by tests (`test_stance_snapshot.py`), and is
already wired into the preview tooling below; it just isn't wired into a real endpoint yet since
there's no `stances` table to read from. In the meantime, three scripts run the real prompts
against real sources without
the database wiring, all sharing the same `run_pipeline`/`render_report` core in
`backend/scripts/preview_pipeline.py` so they can't drift from each other:
`preview_pipeline.py` itself (CLI, one URL), `preview_server.py` (a local browser form on port
8010 — paste a URL instead of typing a command), and `preview_batch.py` (several URLs at once,
rendered as tabs in one HTML file, for side-by-side manual eval). Claim analyzer always runs on
every due claim, uncapped — `--skip-analysis` is the only opt-out, for faster iteration on claim
finder/stance extractor alone. None of the three persists anything; see their own docstrings. The prompt lab
below is a further interface onto the same core, adding editable prompts.

### Prompt lab (`promptlab/`)

A separate local web app for iterating on the prompts themselves, distinct from the three
preview scripts above: edit a pass's system prompt in the browser, run it against a real URL,
and get a file to hand to Claude Code for the next round of edits. `promptlab/README.md` is the
reference; the short version is `cd promptlab && ./run.sh` (port 8020), and every run writes
`promptlab/runs/<run-id>/` containing `run.md` (prompt text used, a unified diff against the
prompt in code, every claim/stance with quotes, verdicts, an empty review-notes section),
`run.json`, `source.txt`, and `report.html`. `promptlab/runs/latest.md` always points at the
newest one.

It is a separate app, not a separate pipeline: it calls `preview_pipeline.run_pipeline` like
the other three, so an experiment exercises the real passes. The footprint inside the backend is
one seam: `extract_claims`, `extract_stances`, `resolve_claim` and `analyze_analyst` each take
optional `system_prompt`/`model` arguments that override the module constant (now publicly
named, e.g. `CLAIM_FINDER_SYSTEM_PROMPT`) and `app/config.py`, and `preview_pipeline`'s
`PromptOverrides` threads a whole run's worth of them through, alongside `prefetched_source`
for the lab's per-URL transcript cache. Production callers pass none of these and behave exactly
as before. Editing a prompt in the lab never writes back to `app/llm/*.py`; promoting an edit
into the committed prompt is a deliberate, separate step, which is the point of keeping the runs
as files. Meta-analyst is not in the lab (it reads a stored claim history that doesn't exist
yet), though its function carries the same seam.

**Pinning claims to iterate on the claim analyzer alone**: because claim finder isn't
deterministic (the same source can extract a different claim set run to run), re-running the
whole pipeline on every claim-analyzer edit lets the claim set itself drift, confounding the
comparison. The "Past runs" tab lets you pin any prior pipeline run's already-extracted claims
(`run.json`'s `claims[].claim` is already `ClaimExtraction`-shaped, so a run doubles as a saved
claim set — no separate storage) instead of re-running claim finder: `run_pipeline`'s
`prefetched_claims` param skips straight to per-claim resolution against that fixed set. Pinning
locks the lab to pipeline mode and disables the claim finder tab for that run (it can't run once
claims are pinned); "Unpin" or switching to raw mode clears it. `pinned_from_run_id` is recorded
on the resulting run so `run.md` shows which claim set an analyzer experiment ran against.

**`backend/scripts/run_claimanalyzer_only.py`** is the terminal-only equivalent of the same idea,
for scripting rather than the browser loop: takes a `run_claimfinder_only.py` output file plus an
optional `--prompt-file` override and resolves each claim via the same `_check_claim` path,
without needing the lab server running.

**Frozen claim-finder dataset for claim-analyzer testing**:
`backend/scripts/output/shortset_claims/` holds `run_claimfinder_only.py` output already run
against the 10 "short pick" videos in `testing/analyst-test-set.md` (one per channel in the
primary set, using their cached transcripts) — 37 claims total, indexed in that directory's
`manifest.json` (channel, video id, title, published date, claim count, file path), with usage
notes in its own `README.md`. Each `<channel>_<video_id>.json` file is already
`run_claimanalyzer_only.py`-shaped, so claim-analyzer prompt work can run against this fixed set
without re-running the non-deterministic claim finder each time. Regenerate it by re-running
`run_claimfinder_only.py` over the same 10 URLs, one process, sequentially (never in parallel —
see `testing/README.md`).

`annotate_eval_batch.py` is a fourth, separate thing: it layers a **hand-written** review of the
prompts' output onto a `preview_batch.py` report (per-claim notes, a per-source summary, and a
leading findings tab). The notes are keyed by panel/claim index and are specific to one batch:
re-running `preview_batch.py` regenerates the report from scratch and invalidates them, so the
review has to be redone against the new output. `scripts/output/eval-batch.html` carries the
first such review, covering 5 videos / 42 claims; its findings tab is the current record of what
the prompts get right and where the claim schema falls short (missing conviction field,
composite claims sharing one verdict, no link between mutually exclusive scenarios, target
window doubling as the price baseline).
