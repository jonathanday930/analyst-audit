#!/usr/bin/env python3
"""Batch version of preview_pipeline.py: run the real pipeline against several video/blog URLs
in one go and render every result as a tab in a single HTML file, so a batch of runs can be
eyeballed side by side for manual eval. Imports `run_pipeline` and the card-rendering helpers
from preview_pipeline.py rather than duplicating pipeline or rendering logic — a third
interface onto the same code, not a separate tool.

Same scope as preview_pipeline.py/preview_server.py: a testing/validation tool for the
claim_finder/stance_extractor/claim_analyzer prompts, not production wiring. Nothing is written
to the database. Runs sequentially (not concurrently) — the claim analyzer's web search + Claude
API calls easily dominate wall-clock time for one source already, and running several sources at
once would parallelize against the same Anthropic API key/rate limit for no real benefit here.

Usage:
    cd backend && source .venv/bin/activate
    python scripts/preview_batch.py URL1 URL2 URL3 ...
    python scripts/preview_batch.py --source URL1 "Some Analyst" --source URL2 "" ...
    python scripts/preview_batch.py URL1 URL2 --skip-analysis --out batch.html

A bare positional URL gets no label (the tab shows the fetched video/post title only); use
repeated `--source URL LABEL` pairs when you want a label (e.g. the analyst/channel name)
alongside a particular URL — pass "" for no label on that one. Positional URLs and --source
pairs can be mixed; order is preserved.

A source that fails to fetch doesn't abort the batch — it gets its own tab with the error
instead, same "one failure doesn't take down the others" approach used elsewhere in this
codebase (see EvaluationResult in ../../youtube_fact_checker).

Requires ANTHROPIC_API_KEY (backend/.env) and network access, same as the other two scripts.
"""

from __future__ import annotations

import argparse
import html
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.sources.fetcher import SourceFetchError
from preview_pipeline import OUTPUT_DIR, PipelineResult, _claim_card, _esc, _slugify, _stance_card, run_pipeline

_STYLE = """\
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  :root {
    --bg: #101418; --card: #1b2129; --card-hover: #212832; --border: #2a323d;
    --text: #e7ebf0; --text-muted: #8b96a3; --text-faint: #5b6572;
    --accent: #e3a63a; --accent-soft: rgba(227,166,58,0.14);
    --good: #4fbf7a; --good-soft: rgba(79,191,122,0.14);
    --bad: #e0616b; --bad-soft: rgba(224,97,107,0.14);
    --pending: #8b96a3; --pending-soft: rgba(139,150,163,0.12);
  }
  body { font-family: 'Space Grotesk', system-ui, sans-serif; background: var(--bg); color: var(--text); }
  .mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { color: #f0bb5e; }
  .shell { display: flex; min-height: 100vh; }
  .tabs { width: 240px; flex-shrink: 0; border-right: 1px solid var(--border); padding: 20px 12px; position: sticky; top: 0; height: 100vh; overflow-y: auto; }
  .tabs h1 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-faint); margin: 0 0 14px; padding: 0 8px; }
  .tab-btn {
    display: block; width: 100%; text-align: left; background: none; border: none; border-radius: 7px;
    color: var(--text-muted); font-family: inherit; font-size: 13px; padding: 9px 10px; margin-bottom: 3px;
    cursor: pointer; line-height: 1.35;
  }
  .tab-btn:hover { background: var(--card-hover); }
  .tab-btn.active { background: var(--card); color: var(--text); }
  .tab-btn .tab-label { display: block; font-weight: 600; color: var(--text); margin-bottom: 2px; }
  .tab-btn .tab-meta { display: block; font-size: 11px; color: var(--text-faint); }
  .tab-btn .tab-meta.tab-error { color: var(--bad); }
  .panels { flex: 1; min-width: 0; }
  .panel { display: none; max-width: 880px; margin: 0 auto; padding: 32px 28px 80px; }
  .panel.active { display: block; }
  .header { border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 28px; }
  .header h2 { font-size: 20px; margin: 0 0 6px; }
  .meta-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; color: var(--text-muted); font-size: 13px; }
  .badge { display: inline-block; padding: 3px 9px; border-radius: 5px; font-size: 11px; font-weight: 600; letter-spacing: 0.02em; }
  .badge--good { color: var(--good); background: var(--good-soft); }
  .badge--bad { color: var(--bad); background: var(--bad-soft); }
  .badge--pending { color: var(--pending); background: var(--pending-soft); }
  .badge--accent { color: var(--accent); background: var(--accent-soft); }
  .badge--faint { color: var(--text-faint); background: rgba(91,101,114,0.12); }
  .badge--outline { color: var(--text-muted); background: none; border: 1px solid var(--border); }
  section { margin-bottom: 36px; }
  section > h3 { font-size: 14px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin: 0 0 14px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; margin-bottom: 12px; }
  .card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
  .card-title { font-size: 15px; font-weight: 600; }
  .badge-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .field { margin-top: 10px; font-size: 13.5px; line-height: 1.5; }
  .field-label { color: var(--text-faint); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }
  .quotes { margin-top: 6px; }
  blockquote { margin: 0 0 6px; padding: 8px 12px; border-left: 2px solid var(--border); color: var(--text-muted); font-size: 13px; font-style: italic; }
  .rationale { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); font-size: 13.5px; color: var(--text-muted); }
  .empty { color: var(--text-faint); font-size: 13.5px; font-style: italic; }
  .run-note { color: var(--text-faint); font-size: 12px; margin-top: 4px; }
  .error-box { background: var(--bad-soft); border: 1px solid var(--bad); color: var(--bad); border-radius: 8px; padding: 14px 16px; font-size: 13.5px; }
  details.run-log { margin-top: 24px; }
  details.run-log summary { cursor: pointer; color: var(--text-muted); font-size: 12.5px; }
  details.run-log ol { margin: 10px 0 0; padding-left: 20px; color: var(--text-muted); font-size: 12.5px; line-height: 1.7; }
  .footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border); color: var(--text-faint); font-size: 12px; }
</style>
"""

_PAGE_TEMPLATE = """\
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Batch pipeline preview ({count} sources)</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap">
{style}
</head>
<body>
<div class="shell">
  <nav class="tabs">
    <h1>Sources ({count})</h1>
    {tab_buttons}
  </nav>
  <div class="panels">
    {panels}
  </div>
</div>
<script>
function showTab(i) {{
  document.querySelectorAll('.tab-btn').forEach(function(el, idx) {{ el.classList.toggle('active', idx === i); }});
  document.querySelectorAll('.panel').forEach(function(el, idx) {{ el.classList.toggle('active', idx === i); }});
}}
showTab(0);
</script>
</body>
</html>
"""


@dataclass
class BatchItem:
    label: str
    url: str
    result: PipelineResult | None
    error: str | None


def _run_one(label: str, url: str, *, skip_analysis: bool) -> BatchItem:
    print(f"\n=== {label or url} ===")
    try:
        result = run_pipeline(url, analyst_name=label or "(unlabeled)", skip_analysis=skip_analysis, on_step=print)
        return BatchItem(label=label, url=url, result=result, error=None)
    except SourceFetchError as exc:
        print(f"  error: {exc}")
        return BatchItem(label=label, url=url, result=None, error=str(exc))


def _tab_button(index: int, item: BatchItem) -> str:
    if item.error:
        title = item.label or item.url
        meta = '<span class="tab-meta tab-error">fetch failed</span>'
    else:
        title = item.result.source.title
        meta = f'<span class="tab-meta">{_esc(item.label)} · {len(item.result.checked_claims)} claims · {len(item.result.checked_stances)} stances</span>' if item.label else f'<span class="tab-meta">{len(item.result.checked_claims)} claims · {len(item.result.checked_stances)} stances</span>'
    return (
        f'<button class="tab-btn{" active" if index == 0 else ""}" onclick="showTab({index})">'
        f'<span class="tab-label">{_esc(title)}</span>{meta}'
        "</button>"
    )


def _panel(index: int, item: BatchItem, models: dict[str, str]) -> str:
    if item.error:
        body = (
            f'<div class="header"><h2>{_esc(item.label or item.url)}</h2>'
            f'<div class="meta-row"><a href="{html.escape(item.url, quote=True)}" target="_blank" rel="noopener">{_esc(item.url)}</a></div></div>'
            f'<div class="error-box">Couldn\'t fetch this source: {_esc(item.error)}</div>'
        )
        return f'<div class="panel{" active" if index == 0 else ""}">{body}</div>'

    result = item.result
    source = result.source
    claims_html = "\n".join(_claim_card(c) for c in result.checked_claims) or '<div class="empty">No falsifiable claims found in this source.</div>'
    stances_html = "\n".join(_stance_card(c) for c in result.checked_stances) or '<div class="empty">No positions or sentiment reads found in this source.</div>'
    log_html = "".join(f"<li>{_esc(line)}</li>" for line in result.run_log)

    body = f"""\
<div class="header">
  <h2>{_esc(source.title)}</h2>
  <div class="meta-row">
    <span class="badge badge--outline">{source.type.upper()}</span>
    <a href="{html.escape(source.original_url, quote=True)}" target="_blank" rel="noopener">{_esc(source.original_url)}</a>
    <span>·</span>
    <span>Published {source.published_at.isoformat() if source.published_at else "unknown"}</span>
    {f'<span>·</span><span>Analyst: {_esc(item.label)}</span>' if item.label else ""}
  </div>
</div>

<section>
  <h3>Claims ({len(result.checked_claims)})</h3>
  {claims_html}
</section>

<section>
  <h3>Stances / sentiment ({len(result.checked_stances)})</h3>
  {stances_html}
</section>

<details class="run-log">
  <summary>Run log ({len(result.run_log)} steps)</summary>
  <ol>{log_html}</ol>
</details>

<div class="footer">
  Models: claim_finder={models["claim_finder_model"]}, stance_extractor={models["stance_extractor_model"]}, claim_analyzer={models["claim_analyzer_model"]}
</div>
"""
    return f'<div class="panel{" active" if index == 0 else ""}">{body}</div>'


def render_batch(items: list[BatchItem], models: dict[str, str]) -> str:
    tab_buttons = "\n".join(_tab_button(i, item) for i, item in enumerate(items))
    panels = "\n".join(_panel(i, item, models) for i, item in enumerate(items))
    return _PAGE_TEMPLATE.format(count=len(items), style=_STYLE, tab_buttons=tab_buttons, panels=panels)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("urls", nargs="*", help="Bare URLs with no label.")
    parser.add_argument("--source", nargs=2, metavar=("URL", "LABEL"), action="append", default=[], dest="labeled_sources", help='A URL with an explicit label, e.g. --source "https://..." "Some Analyst". Pass "" for no label.')
    parser.add_argument("--skip-analysis", action="store_true", help="Skip claim analyzer entirely for every source — claim finder + stance extractor only (faster/cheaper for iterating on those two prompts).")
    parser.add_argument("--out", default=None, help="Output HTML path (default: scripts/output/batch-<timestamp>.html).")
    parser.add_argument("--no-open", action="store_true", help="Don't open the report in a browser automatically.")
    args = parser.parse_args()

    sources: list[tuple[str, str]] = [(url, "") for url in args.urls] + [(url, label) for url, label in args.labeled_sources]
    if not sources:
        parser.error("Pass at least one URL, positionally or via --source.")

    items = [_run_one(label, url, skip_analysis=args.skip_analysis) for url, label in sources]

    settings = get_settings()
    models = {
        "claim_finder_model": settings.claim_finder_model,
        "stance_extractor_model": settings.stance_extractor_model,
        "claim_analyzer_model": settings.claim_analyzer_model,
    }

    report_html = render_batch(items, models)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
    out_path.write_text(report_html, encoding="utf-8")
    print(f"\nBatch report written to {out_path}")

    if not args.no_open:
        webbrowser.open(f"file://{out_path.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
