#!/usr/bin/env python3
"""Standalone preview of the real pipeline — claim finder, stance extractor, and claim analyzer
— run against one real video or blog URL, using
the actual prompts in app/llm/. Renders a static HTML report styled with the app's real design
tokens (design/mockup/prototype/index.html) so the AI's extracted claims and reasoning fields
can be visually spot-checked against the source.

This is a testing/validation tool, not production wiring: nothing is written to the database.
The real run_claim_finder/run_stance_extractor/run_claim_analyzer job seams (app/jobs/*.py) and
their DB persistence are separate, still-open tasks in TASKS.md, owned by Codex per CLAUDE.md's
Division of labor — this script exists so the prompts themselves can be validated against real
sources before that wiring happens.

Usage:
    cd backend && source .venv/bin/activate
    python scripts/preview_pipeline.py <video-or-blog-url> [--analyst-name NAME] [--out FILE]
    python scripts/preview_pipeline.py <url> --skip-analysis   # claim finder + stance extractor only

Claim analyzer always runs on every due claim — no cap. For a browser form instead of the
command line, see scripts/preview_server.py; for several URLs rendered as tabs in one file, see
scripts/preview_batch.py. Both import `run_pipeline`/`render_report` from this module rather
than duplicating pipeline logic.

Requires ANTHROPIC_API_KEY (backend/.env) and network access — source fetch, price data
(yfinance), and Claude's own web search during claim analysis all hit the network.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.llm.claim_analyzer import CLAIM_ANALYZER_SYSTEM_PROMPT, resolve_claim
from app.llm.claim_finder import CLAIM_FINDER_SYSTEM_PROMPT, extract_claims
from app.llm.schemas import (
    ClaimContext,
    ClaimExtraction,
    ClaimResolution,
    StanceExtraction,
    StanceExtractionList,
    StanceMarketSnapshot,
)
from app.llm.stance_extractor import STANCE_EXTRACTOR_SYSTEM_PROMPT, extract_stances  # noqa: F401 -- kept for when stance extractor is re-enabled, see run_pipeline
from app.prices.price_data import fetch_price_series
from app.prices.stance_snapshot import compute_stance_snapshot, resolve_stance_ticker
from app.prices.ticker_resolver import resolve_tickers
from app.sources.fetcher import FetchedSource, SourceFetchError, fetch_source

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


# --- per-run prompt/model overrides -----------------------------------------------------------


@dataclass(frozen=True)
class PromptOverrides:
    """Per-run replacements for the three passes' system prompts and models. Every field is
    optional; a null field means "use what's in the code / config". Threaded straight through to
    the real pass functions in app/llm/. This is the seam the prompt lab (../../promptlab) runs
    an edited prompt through, so an experiment always exercises the same pipeline the CLI and
    batch runner do, not a parallel copy of it."""

    claim_finder_system: str | None = None
    claim_finder_model: str | None = None
    stance_extractor_system: str | None = None
    stance_extractor_model: str | None = None
    claim_analyzer_system: str | None = None
    claim_analyzer_model: str | None = None


DEFAULT_PROMPTS = {
    "claim_finder": CLAIM_FINDER_SYSTEM_PROMPT,
    "stance_extractor": STANCE_EXTRACTOR_SYSTEM_PROMPT,
    "claim_analyzer": CLAIM_ANALYZER_SYSTEM_PROMPT,
}


# --- claim-analyzer eligibility + execution --------------------------------------------------


def _due_for_check(claim: ClaimExtraction, today: date) -> bool:
    """Preview every extracted claim immediately; concrete windows are derived downstream."""
    return True


def _benchmark_ticker(resolved_ticker: str | None, asset_description: str) -> str:
    """Coarse equity-vs-crypto heuristic for picking a benchmark, per CLAUDE.md's "Evaluation
    includes a benchmark comparison" note (SPY for equity-ish claims, a major crypto for crypto
    claims). Good enough for this preview tool; not meant to be the final benchmark-selection
    logic."""
    text = f"{resolved_ticker or ''} {asset_description}".lower()
    crypto_markers = ("btc", "bitcoin", "eth", "ethereum", "crypto", "-usd")
    return "BTC-USD" if any(marker in text for marker in crypto_markers) else "SPY"


@dataclass
class CheckedClaim:
    claim: ClaimExtraction
    resolution: ClaimResolution | None
    used_web_search: bool
    skip_reason: str | None
    benchmark_ticker: str | None = None


def _check_claim(
    claim: ClaimExtraction,
    *,
    published_at: date | None,
    today: date,
    overrides: PromptOverrides = PromptOverrides(),
) -> CheckedClaim:
    tickers = resolve_tickers(asset_description=claim.asset_description, suggested_ticker=claim.suggested_ticker)
    start = published_at or today
    end = today

    price_series = (
        [series for t in tickers if (series := fetch_price_series(ticker=t, start=start, end=end)) is not None]
        if start <= end
        else []
    )
    benchmark_ticker = _benchmark_ticker(tickers[0] if tickers else None, claim.asset_description)
    benchmark_series = fetch_price_series(ticker=benchmark_ticker, start=start, end=end) if start <= end else None

    context = ClaimContext(
        asset_description=claim.asset_description,
        suggested_ticker=claim.suggested_ticker,
        condition_trigger=claim.condition_trigger,
        claim=claim.claim,
        horizon=claim.horizon,
        trigger_status="waiting" if claim.condition_trigger else None,
        published_at=published_at,
    )
    resolution, used_web_search = resolve_claim(
        claim=context,
        as_of=today,
        price_series=price_series,
        benchmark_series=benchmark_series,
        benchmark_ticker=benchmark_ticker,
        system_prompt=overrides.claim_analyzer_system,
        model=overrides.claim_analyzer_model,
    )
    return CheckedClaim(claim, resolution, used_web_search, None, benchmark_ticker)


@dataclass
class CheckedStance:
    stance: StanceExtraction
    snapshot: StanceMarketSnapshot | None
    skip_reason: str | None


def _check_stance(stance: StanceExtraction, *, call_date: date, today: date) -> CheckedStance:
    """Deterministic, no LLM call: resolve a ticker from the stance's asset_description/scope,
    then pull real price history since call_date. `call_date` is the source's published date
    (or today, if unknown) — see run_pipeline."""
    ticker = resolve_stance_ticker(stance)
    if ticker is None:
        return CheckedStance(stance, None, "No resolvable ticker for this stance.")
    snapshot = compute_stance_snapshot(ticker=ticker, call_date=call_date, as_of=today)
    if snapshot is None:
        return CheckedStance(stance, None, f"No price data available for {ticker} since {call_date.isoformat()}.")
    return CheckedStance(stance, snapshot, None)


@dataclass
class PipelineResult:
    source: FetchedSource
    checked_claims: list[CheckedClaim]
    checked_stances: list[CheckedStance]
    run_log: list[str] = field(default_factory=list)


def run_pipeline(
    url: str,
    *,
    analyst_name: str,
    skip_analysis: bool,
    on_step: Callable[[str], None] | None = None,
    overrides: PromptOverrides | None = None,
    prefetched_source: FetchedSource | None = None,
    prefetched_claims: list[ClaimExtraction] | None = None,
) -> PipelineResult:
    """The actual pipeline: fetch source -> claim finder -> stance extractor -> claim analyzer
    for every due claim (no cap — see CLAUDE.md's Claim analyzer stage; skip_analysis=True is
    the only way to opt out, for faster iteration on claim finder/stance extractor alone).
    Shared by the CLI (`main`, below), the browser form (scripts/preview_server.py), and the
    batch runner (scripts/preview_batch.py) so none of the three can drift from each other.
    Raises SourceFetchError (unhandled here) on a bad URL/unfetchable source — callers decide
    how to present that. `analyst_name` is not used by the pipeline itself (nothing here
    matches or creates a real analyst record); it's threaded through only so callers can pass
    it straight to render_report without holding onto it separately.

    `overrides` swaps in edited system prompts/models for one run (see PromptOverrides);
    `prefetched_source` skips the network fetch when the caller already has the source text
    cached. `prefetched_claims` skips claim finder entirely and resolves these claims instead —
    for iterating on the claim analyzer prompt alone against a fixed, already-extracted claim
    set (claim finder isn't deterministic, so re-running it on every analyzer edit would let the
    claim set itself drift, confounding the comparison). All three exist for the prompt lab and
    default to the normal behaviour."""
    log: list[str] = []
    overrides = overrides or PromptOverrides()

    def step(message: str) -> None:
        log.append(message)
        if on_step:
            on_step(message)

    if prefetched_source is not None:
        source = prefetched_source
        step(f"Using cached source text for {url}")
    else:
        step(f"Fetching source: {url}")
        source = fetch_source(url)
    step(f'"{source.title}" ({source.type}, published {source.published_at or "unknown"}, {len(source.content)} chars)')

    today = datetime.now(timezone.utc).date()

    if prefetched_claims is not None:
        claims = prefetched_claims
        step(f"Using {len(claims)} pinned claim(s) — skipping claim finder")
    else:
        step("Running claim finder...")
        claim_result = extract_claims(
            title=source.title,
            published_at=source.published_at,
            fetched_at=today,
            source_text=source.content,
            system_prompt=overrides.claim_finder_system,
            model=overrides.claim_finder_model,
        )
        claims = claim_result.claims
        step(f"{len(claims)} claim(s) extracted")

    # Stance extractor disabled for now — see CLAUDE.md / TASKS.md for when to re-enable.
    # step("Running stance extractor...")
    # stance_result = extract_stances(
    #     source_text=source.content,
    #     system_prompt=overrides.stance_extractor_system,
    #     model=overrides.stance_extractor_model,
    # )
    # step(f"{len(stance_result.stances)} stance(s) extracted")
    stance_result = StanceExtractionList(stances=[])

    # Deterministic, no LLM cost — runs even under skip_analysis, unlike claim analyzer below.
    call_date = source.published_at or today
    checked_stances = [_check_stance(s, call_date=call_date, today=today) for s in stance_result.stances]

    checked_claims: list[CheckedClaim] = []
    if skip_analysis:
        checked_claims = [CheckedClaim(c, None, False, "Skipped (claim analyzer not run this pass).") for c in claims]
    else:
        due_count = sum(1 for c in claims if _due_for_check(c, today))
        if due_count:
            step(f"{due_count} claim(s) due for a check — running claim analyzer on all of them")
        checked_so_far = 0
        for claim in claims:
            if not _due_for_check(claim, today):
                checked_claims.append(_check_claim(claim, published_at=source.published_at, today=today, overrides=overrides))
                continue
            checked_so_far += 1
            step(f"[{checked_so_far}/{due_count}] Checking {claim.asset_description}...")
            checked_claims.append(_check_claim(claim, published_at=source.published_at, today=today, overrides=overrides))

    return PipelineResult(source=source, checked_claims=checked_claims, checked_stances=checked_stances, run_log=log)


# --- HTML rendering (design tokens copied from design/mockup/prototype/index.html) -----------

_PAGE_TEMPLATE = """\
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pipeline preview — {title}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  :root {{
    --bg: #101418; --bg2: #171c22; --card: #1b2129; --card-hover: #212832;
    --border: #2a323d; --text: #e7ebf0; --text-muted: #8b96a3; --text-faint: #5b6572;
    --accent: #e3a63a; --accent-soft: rgba(227,166,58,0.14);
    --good: #4fbf7a; --good-soft: rgba(79,191,122,0.14);
    --bad: #e0616b; --bad-soft: rgba(224,97,107,0.14);
    --pending: #8b96a3; --pending-soft: rgba(139,150,163,0.12);
  }}
  body {{ font-family: 'Space Grotesk', system-ui, sans-serif; background: var(--bg); color: var(--text); }}
  .mono {{ font-family: 'JetBrains Mono', ui-monospace, monospace; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ color: #f0bb5e; }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 32px 20px 80px; }}
  .header {{ border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 28px; }}
  .header h1 {{ font-size: 20px; margin: 0 0 6px; }}
  .meta-row {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; color: var(--text-muted); font-size: 13px; }}
  .badge {{ display: inline-block; padding: 3px 9px; border-radius: 5px; font-size: 11px; font-weight: 600; letter-spacing: 0.02em; }}
  .badge--good {{ color: var(--good); background: var(--good-soft); }}
  .badge--bad {{ color: var(--bad); background: var(--bad-soft); }}
  .badge--pending {{ color: var(--pending); background: var(--pending-soft); }}
  .badge--accent {{ color: var(--accent); background: var(--accent-soft); }}
  .badge--faint {{ color: var(--text-faint); background: rgba(91,101,114,0.12); }}
  .badge--outline {{ color: var(--text-muted); background: none; border: 1px solid var(--border); }}
  section {{ margin-bottom: 36px; }}
  section > h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin: 0 0 14px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; margin-bottom: 12px; }}
  .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }}
  .card-title {{ font-size: 15px; font-weight: 600; }}
  .badge-row {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .field {{ margin-top: 10px; font-size: 13.5px; line-height: 1.5; }}
  .field-label {{ color: var(--text-faint); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }}
  .quotes {{ margin-top: 6px; }}
  blockquote {{ margin: 0 0 6px; padding: 8px 12px; border-left: 2px solid var(--border); color: var(--text-muted); font-size: 13px; font-style: italic; }}
  .rationale {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); font-size: 13.5px; color: var(--text-muted); }}
  .empty {{ color: var(--text-faint); font-size: 13.5px; font-style: italic; }}
  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border); color: var(--text-faint); font-size: 12px; }}
  .run-note {{ color: var(--text-faint); font-size: 12px; margin-top: 4px; }}
  .nav {{ margin-bottom: 20px; font-size: 13px; }}
  details.run-log {{ margin-top: 24px; }}
  details.run-log summary {{ cursor: pointer; color: var(--text-muted); font-size: 12.5px; }}
  details.run-log ol {{ margin: 10px 0 0; padding-left: 20px; color: var(--text-muted); font-size: 12.5px; line-height: 1.7; }}
</style>
</head>
<body>
<div class="wrap">
  {nav_html}
  <div class="header">
    <h1>{title}</h1>
    <div class="meta-row">
      <span class="badge badge--outline">{source_type_label}</span>
      <a href="{url}" target="_blank" rel="noopener">{url}</a>
      <span>·</span>
      <span>Published {published}</span>
      <span>·</span>
      <span>Analyst: {analyst_name}</span>
    </div>
  </div>

  <section>
    <h2>Claims ({claim_count})</h2>
    {claims_html}
  </section>

  <section>
    <h2>Stances / sentiment ({stance_count})</h2>
    {stances_html}
  </section>

  <details class="run-log">
    <summary>Run log ({run_log_count} step{run_log_plural})</summary>
    <ol>{run_log_html}</ol>
  </details>

  <div class="footer">
    Generated {generated_at} — not persisted to any database.<br>
    Models: claim_finder={claim_finder_model}, stance_extractor={stance_extractor_model}, claim_analyzer={claim_analyzer_model}
  </div>
</div>
</body>
</html>
"""


def _esc(value: str | None) -> str:
    return html.escape(value) if value else ""


def _horizon_badge(horizon: str | None) -> str:
    if horizon is None:
        return '<span class="badge badge--outline">HORIZON UNSTATED</span>'
    kind = "badge--pending" if horizon == "short-term" else "badge--accent"
    return f'<span class="badge {kind}">{_esc(horizon.upper())}</span>'


def _condition_badge(condition_trigger: list[str]) -> str:
    if not condition_trigger:
        return '<span class="badge badge--outline">UNCONDITIONAL</span>'
    return '<span class="badge badge--accent">EVENT TRIGGER</span>'


def _outcome_badge(checked: CheckedClaim) -> str:
    if checked.resolution is None:
        return '<span class="badge badge--pending">NOT CHECKED YET</span>'
    res = checked.resolution
    if res.outcome == "trigger_expired":
        return '<span class="badge badge--faint">EXPIRED</span>'
    if res.outcome == "still_pending":
        return '<span class="badge badge--pending">STILL PENDING</span>'
    if res.verdict == "good":
        return '<span class="badge badge--good">GOOD CALL</span>'
    if res.verdict == "bad":
        return '<span class="badge badge--bad">BAD CALL</span>'
    return '<span class="badge badge--outline">AMBIGUOUS</span>'


def _quotes_html(quotes: list[str]) -> str:
    return '<div class="quotes">' + "".join(f"<blockquote>“{_esc(q)}”</blockquote>" for q in quotes) + "</div>"


def _items_html(items: list[str]) -> str:
    return '<ul style="margin:4px 0 0;padding-left:18px;">' + "".join(
        f"<li>{_esc(item)}</li>" for item in items
    ) + "</ul>"


def _claim_card(checked: CheckedClaim) -> str:
    claim = checked.claim
    parts = [
        '<div class="card">',
        '<div class="card-top">',
        f'<div class="card-title mono">{_esc(claim.asset_description)}'
        + (f' <span style="color:var(--text-faint);font-weight:400;">({_esc(", ".join(claim.suggested_ticker))})</span>' if claim.suggested_ticker else "")
        + "</div>",
        f'<div class="badge-row">{_horizon_badge(claim.horizon)}{_condition_badge(claim.condition_trigger)}{_outcome_badge(checked)}</div>',
        "</div>",
    ]
    if claim.condition_trigger:
        parts.append(f'<div class="field"><div class="field-label">Condition / trigger</div>{_items_html(claim.condition_trigger)}</div>')
    parts.append(f'<div class="field"><div class="field-label">Claim</div>{_esc(claim.claim)}</div>')
    parts.append(
        f'<div class="field"><div class="field-label">Horizon window</div>{_esc(claim.horizon)} '
        '(rough dates are derived by the claim analyzer)</div>'
    )
    if claim.grounds:
        items = "".join(f"<li>{_esc(g)}</li>" for g in claim.grounds)
        parts.append(
            '<div class="field"><div class="field-label">Grounds (cited facts)</div>'
            f'<ul style="margin:4px 0 0;padding-left:18px;">{items}</ul></div>'
        )
    if claim.warrant:
        parts.append(f'<div class="field"><div class="field-label">Warrant (grounds to claim)</div>{_items_html(claim.warrant)}</div>')
    if claim.backing:
        parts.append(f'<div class="field"><div class="field-label">Backing (why the warrant holds)</div>{_items_html(claim.backing)}</div>')
    if claim.qualifier or claim.confidence is not None:
        qual = _esc(claim.qualifier) if claim.qualifier else "not stated"
        conf = (
            f'<span class="mono" style="color:var(--accent);">{claim.confidence:.0f}%</span>'
            if claim.confidence is not None
            else ""
        )
        sep = " &nbsp;·&nbsp; " if conf and claim.qualifier else ""
        parts.append(f'<div class="field"><div class="field-label">Qualifier (expressed certainty)</div>{qual}{sep}{conf}</div>')
    if claim.rebuttal_invalidation:
        parts.append(
            '<div class="field"><div class="field-label">Rebuttal / invalidation</div>'
            f'{_items_html(claim.rebuttal_invalidation)}</div>'
        )

    if checked.skip_reason:
        parts.append(f'<div class="rationale">{_esc(checked.skip_reason)}</div>')
    elif checked.resolution:
        res = checked.resolution
        rationale = f'<div class="rationale"><strong>{_esc(res.outcome)}</strong>{" · " + _esc(res.verdict) if res.verdict else ""}: {_esc(res.rationale)}'
        if res.benchmark:
            b = res.benchmark
            beat = "beat" if b.beat_benchmark else ("trailed" if b.beat_benchmark is False else "vs.")
            claim_ret = f"{b.claim_return_pct:+.1f}%" if b.claim_return_pct is not None else "n/a"
            rationale += f'<br>Benchmark ({_esc(b.benchmark_ticker)}): {b.benchmark_return_pct:+.1f}% — claim asset {claim_ret} ({beat} benchmark)'
        rationale += f'<br><span class="run-note">web search used: {"yes" if checked.used_web_search else "no"}</span>'
        rationale += "</div>"
        parts.append(rationale)

    parts.append("</div>")
    return "\n".join(parts)


def _snapshot_html(checked: CheckedStance) -> str:
    if checked.snapshot is None:
        return f'<div class="run-note">{_esc(checked.skip_reason or "No market snapshot available.")}</div>'
    s = checked.snapshot
    sign = "+" if s.change_since_call_pct >= 0 else ""
    return (
        '<div class="field"><div class="field-label">Market snapshot since call</div>'
        f'<span class="mono">{_esc(s.ticker)}</span> — '
        f'called at ${s.call_price:,.2f} on {s.call_date.isoformat()}, now ${s.current_price:,.2f} '
        f'({sign}{s.change_since_call_pct:.1f}%)'
        f'<br>high ${s.high_since_call:,.2f} ({s.high_date.isoformat()}) '
        f'&nbsp;·&nbsp; low ${s.low_since_call:,.2f} ({s.low_date.isoformat()}) '
        f'&nbsp;·&nbsp; {s.days_since_call}d since call'
        "</div>"
    )


def _stance_card(checked: CheckedStance) -> str:
    stance = checked.stance
    if stance.kind == "position":
        kind_badge = '<span class="badge badge--accent">POSITION</span>'
        direction_badge = f'<span class="badge {"badge--good" if stance.direction == "long" else "badge--bad" if stance.direction == "short" else "badge--outline"}">{_esc((stance.direction or "").upper())}</span>'
        title = _esc(stance.asset_description) + (f' <span style="color:var(--text-faint);font-weight:400;">({_esc(stance.suggested_ticker)})</span>' if stance.suggested_ticker else "")
        badges = kind_badge + direction_badge
    else:
        kind_badge = '<span class="badge badge--outline">SENTIMENT</span>'
        sentiment_kind = {"bullish": "badge--good", "bearish": "badge--bad"}.get(stance.sentiment or "", "badge--pending")
        sentiment_badge = f'<span class="badge {sentiment_kind}">{_esc((stance.sentiment or "").upper())}</span>'
        title = _esc(stance.asset_description or stance.scope or "the market")
        badges = kind_badge + sentiment_badge

    return (
        '<div class="card">'
        '<div class="card-top">'
        f'<div class="card-title mono">{title}</div>'
        f'<div class="badge-row">{badges}</div>'
        "</div>"
        f'<div class="field"><div class="field-label">Evidence</div>{_quotes_html(stance.supporting_quotes)}</div>'
        f'{_snapshot_html(checked)}'
        "</div>"
    )


def render_report(
    *,
    source: FetchedSource,
    checked_claims: list[CheckedClaim],
    checked_stances: list[CheckedStance],
    analyst_name: str,
    models: dict[str, str],
    run_log: list[str] | None = None,
    nav_html: str = "",
) -> str:
    claims_html = "\n".join(_claim_card(c) for c in checked_claims) or '<div class="empty">No falsifiable claims found in this source.</div>'
    stances_html = "\n".join(_stance_card(c) for c in checked_stances) or '<div class="empty">No positions or sentiment reads found in this source.</div>'
    log = run_log or []
    return _PAGE_TEMPLATE.format(
        title=_esc(source.title),
        source_type_label=source.type.upper(),
        url=html.escape(source.original_url, quote=True),
        published=source.published_at.isoformat() if source.published_at else "unknown",
        analyst_name=_esc(analyst_name),
        claim_count=len(checked_claims),
        claims_html=claims_html,
        stance_count=len(checked_stances),
        stances_html=stances_html,
        run_log_count=len(log),
        run_log_plural="" if len(log) == 1 else "s",
        run_log_html="".join(f"<li>{_esc(line)}</li>" for line in log),
        nav_html=nav_html,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        **models,
    )


# --- CLI ---------------------------------------------------------------------------------


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "source"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="A YouTube video URL or blog post URL.")
    parser.add_argument("--analyst-name", default="(unlabeled — for display only)", help="Label only; this script doesn't match against or create a real analyst record.")
    parser.add_argument("--out", default=None, help="Output HTML path (default: scripts/output/<slug>-<timestamp>.html).")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip claim analyzer entirely — claim finder + stance extractor only (faster/cheaper for iterating on those two prompts).")
    parser.add_argument("--no-open", action="store_true", help="Don't open the report in a browser automatically.")
    args = parser.parse_args()

    try:
        result = run_pipeline(
            args.url,
            analyst_name=args.analyst_name,
            skip_analysis=args.skip_analysis,
            on_step=print,
        )
    except SourceFetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    settings = get_settings()
    models = {
        "claim_finder_model": settings.claim_finder_model,
        "stance_extractor_model": settings.stance_extractor_model,
        "claim_analyzer_model": settings.claim_analyzer_model,
    }

    report_html = render_report(
        source=result.source,
        checked_claims=result.checked_claims,
        checked_stances=result.checked_stances,
        analyst_name=args.analyst_name,
        models=models,
        run_log=result.run_log,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"{_slugify(result.source.title)}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
    out_path.write_text(report_html, encoding="utf-8")
    print(f"Report written to {out_path}")

    if not args.no_open:
        webbrowser.open(f"file://{out_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
