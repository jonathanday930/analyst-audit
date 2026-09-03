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

Per claim: asset/instrument description + best-guess ticker (kept as a plain best guess, same
role as `suggestedTicker` in `youtube_fact_checker` — final resolution to a real tradeable
symbol still happens in a separate deterministic step, not at extraction time), condition/
trigger (freeform text — a price level OR a real-world event, not necessarily numeric),
expected outcome, horizon (short-term/swing vs. long-term/structural — captured as a raw fact
from the analyst's own wording, not a judgment call), timeframe as stated, and a target **window**
(earliest/latest date) sized to how vague the stated timeframe was ("in 6 months" → a wide
window; "by June 15th" → a tight one) rather than one hard target date — a analyst shouldn't be
marked wrong just because an outcome landed slightly outside a fuzzy self-stated timeframe. Plus
source metadata: analyst id, source type, source url/id, published date — attached in code, not
part of the model's reasoning.

Conditional claims (an "if X happens" trigger) need a second deadline, separate from the target
window above: how long the *condition itself* stays live before the claim goes stale, not just
how long to wait for the outcome once the condition fires. "If the Fed hikes, stocks crash" made
today isn't a fair thing to grade if the Fed doesn't hike for another decade — the market context
that motivated the call is long gone by then. If the analyst stated an explicit timeframe for the
condition, use it as the trigger deadline; otherwise default to a fixed staleness period (e.g. 12
months from the claim date). A claim whose trigger deadline passes with the condition never
firing resolves to a distinct **expired** state — moot, not folded into good/bad.

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
are display-only strings in the mockup that need to become structured fields in the real schema:
- `windowText` (e.g. "Oct 15 – Dec 20, 2026", "Open-ended — rechecked periodically", "Trigger
  not yet met") needs real `target_window_start`/`target_window_end` dates, nullable for
  open-ended or not-yet-triggered claims — see the fuzzy-window rationale in the claim schema
  section above.
- Conditional claims need trigger lifecycle fields, per the trigger-deadline rationale in the
  claim schema section above: `trigger_status` (waiting / triggered / expired),
  `trigger_observed_at`, and a computed `trigger_deadline` (from the analyst's stated condition
  timeframe, or the default staleness period if none was stated). `status` needs a third value,
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
layer (real schema, CRUD, the screens above wired to real data). The claim finder / claim
analyzer / meta analyst analysis prompts, the actual AI extraction and evaluation logic, are being
handled separately, iteratively, elsewhere. Codex's backend work should leave clean seams (API
endpoints, job hooks) for those to plug into rather than building throwaway stand-ins for them,
but shouldn't attempt to implement the extraction/evaluation prompts itself.

## Status

UI/UX design is done (see prototype above). Backend, database, and real frontend build have not
started; see `TASKS.md` for the current build-out backlog, split as described in "Division of
labor" above.
