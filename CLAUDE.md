# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## What this is

A track-record system for finance "gurus" (YouTube channels, blogs — Twitter/X explicitly out
of scope for now). It extracts every falsifiable claim a guru makes from their long-form
content, checks over time whether each one panned out, and rolls that up into a per-guru
reliability score. The eventual goal is to compile scores across several gurus to help judge
whether a current buy/sell idea is worth acting on — but that final synthesis step is deferred
(see MVP scope below).

This is a sibling project to `../youtube_fact_checker`, which does single-video "would
following this video's advice have paid off" analysis. `AnalystAudit` is a different product,
not an evolution of it — it's stateful (persistent claim history per guru) where the other is
deliberately stateless, and its claim schema is intentionally *not* a trade-action framing (see
Claim schema below). Reusable infrastructure — the Claude structured-output client pattern,
ticker resolution, yfinance price fetching, YouTube transcript/metadata fetching — should be
ported over from `youtube_fact_checker`'s backend rather than rebuilt from scratch; the
extraction/evaluation prompts and schemas should not be reused as-is.

## Architecture: three pipeline stages

1. **Claim finder** — extracts claims from one source (a video transcript or blog post),
   deliberately does NOT categorize by asset class/topic, does NOT collapse multiple scenarios
   in one video into a single "base case" (each distinct condition+outcome pair is recorded as
   its own claim, even if two claims from the same guru/video would look contradictory), and
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
3. **Meta guru analysis** — reads a guru's whole claim history (raw claims + resolved verdicts)
   and derives categorization/scoring after the fact (e.g. "good at crypto, bad at macro calls")
   — categorization is deliberately NOT baked in at claim-finder time, so the categorization
   scheme can change later without needing to re-extract anything.

A fourth stage — combining several trusted gurus' currently-open claims into a "does this
buy/sell make sense right now" read — was discussed and explicitly deferred. Once 1-3 exist,
it's expected to be a prompt over existing data, not new infrastructure.

### Onboarding a new guru: channel/feed URL, not a single video URL

Adding a brand-new guru asks for a URL that lets claim finder keep tracking them afterward, not
just seed one claim: a **YouTube channel URL** for video-based gurus, and a **blog RSS/feed
URL** for blog-based ones (most blogging platforms generate one — e.g. `/feed` or `/rss` — even
when it isn't linked from the page). Feed URLs were chosen over scraping the blog's homepage
because they're a structured, standard mechanism for "here are all my posts" rather than
something that breaks whenever a site's layout changes. Adding a single new post/video to a
guru you already track (via that guru's own profile page, not the "Add analyst" flow) still
asks for the one specific video/post URL, since there's no channel-level re-registration needed
there.

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
from the guru's own wording, not a judgment call), timeframe as stated, and a target **window**
(earliest/latest date) sized to how vague the stated timeframe was ("in 6 months" → a wide
window; "by June 15th" → a tight one) rather than one hard target date — a guru shouldn't be
marked wrong just because an outcome landed slightly outside a fuzzy self-stated timeframe. Plus
source metadata: guru id, source type, source url/id, published date — attached in code, not
part of the model's reasoning.

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

## Status

Pre-code. Architecture and claim schema above were worked out in design conversation; nothing
has been implemented yet. No backend/frontend scaffolding exists in this repo yet.
