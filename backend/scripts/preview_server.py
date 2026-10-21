#!/usr/bin/env python3
"""Local-only browser UI for scripts/preview_pipeline.py: paste a YouTube (or blog) URL into a
form instead of running the CLI, and get back the same styled HTML report. Imports
`run_pipeline`/`render_report` from preview_pipeline.py rather than duplicating pipeline logic
— this is a second interface onto the same code, not a separate tool.

Same scope as preview_pipeline.py: a testing/validation tool for the claim_finder/
stance_extractor/claim_analyzer prompts, not production wiring. Nothing is written to the real
database; each run's report is only saved as a local file (scripts/output/), same as the CLI.

Usage:
    cd backend && source .venv/bin/activate
    python scripts/preview_server.py            # http://127.0.0.1:8010
    python scripts/preview_server.py --port 8020

Requires ANTHROPIC_API_KEY (backend/.env), same as the CLI script. Runs on a different port
than the real app's dev server (8000/5173) so both can run at once.
"""

from __future__ import annotations

import argparse
import html
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.llm.client import AnthropicNotConfiguredError
from app.sources.fetcher import SourceFetchError
from preview_pipeline import OUTPUT_DIR, _slugify, render_report, run_pipeline

app = FastAPI(title="AnalystAudit pipeline preview")

_STYLE = """\
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  :root {
    --bg: #101418; --card: #1b2129; --border: #2a323d; --text: #e7ebf0;
    --text-muted: #8b96a3; --text-faint: #5b6572; --accent: #e3a63a;
    --accent-soft: rgba(227,166,58,0.14); --bad: #e0616b; --bad-soft: rgba(224,97,107,0.14);
  }
  body { font-family: 'Space Grotesk', system-ui, sans-serif; background: var(--bg); color: var(--text); }
  .wrap { max-width: 640px; margin: 0 auto; padding: 48px 20px 80px; }
  h1 { font-size: 20px; margin: 0 0 6px; }
  p.sub { color: var(--text-muted); font-size: 13.5px; margin: 0 0 28px; }
  label { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-faint); margin: 18px 0 6px; }
  input[type=text], input[type=number] {
    width: 100%; background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    color: var(--text); font-size: 14px; padding: 10px 12px; font-family: inherit;
  }
  input[type=text]:focus, input[type=number]:focus { outline: none; border-color: var(--accent); }
  .row { display: flex; align-items: center; gap: 8px; margin-top: 18px; }
  .row input[type=checkbox] { width: 16px; height: 16px; }
  .row label { margin: 0; text-transform: none; letter-spacing: normal; font-size: 13.5px; color: var(--text); }
  button {
    margin-top: 28px; width: 100%; padding: 12px; border-radius: 8px; border: none;
    background: var(--accent); color: #171205; font-size: 14px; font-weight: 600; cursor: pointer;
    font-family: inherit;
  }
  button:disabled { opacity: 0.6; cursor: default; }
  .hint { color: var(--text-faint); font-size: 12px; margin-top: 10px; }
  .error { background: var(--bad-soft); border: 1px solid var(--bad); color: var(--bad); border-radius: 8px; padding: 14px 16px; margin-top: 20px; font-size: 13.5px; }
  a { color: var(--accent); }
</style>
"""

_FORM_PAGE = """\
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AnalystAudit pipeline preview</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap">
{style}
</head>
<body>
<div class="wrap">
  <h1>Pipeline preview</h1>
  <p class="sub">Run claim finder, the stance extractor, and (for due claims) claim analyzer against one real source. Nothing is saved to the database.</p>
  <form method="get" action="/run" onsubmit="document.getElementById('go').disabled=true;document.getElementById('go').textContent='Running… this can take a minute or two';">
    <label for="url">Video or blog URL</label>
    <input type="text" id="url" name="url" placeholder="https://www.youtube.com/watch?v=..." required autofocus>

    <label for="analyst_name">Analyst name (label only)</label>
    <input type="text" id="analyst_name" name="analyst_name" placeholder="(unlabeled)">

    <div class="row">
      <input type="checkbox" id="skip_analysis" name="skip_analysis" value="true">
      <label for="skip_analysis">Skip claim analyzer entirely (claim finder + stance extractor only — faster)</label>
    </div>

    <button id="go" type="submit">Run pipeline</button>
    <div class="hint">Claim analyzer runs on every due claim (no cap) and uses web search, so a source with several due claims can take a few minutes.</div>
  </form>
  {error_html}
</div>
</body>
</html>
"""


def _render_form(error: str | None = None) -> str:
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    return _FORM_PAGE.format(style=_STYLE, error_html=error_html)


@app.get("/", response_class=HTMLResponse)
def form() -> str:
    return _render_form()


@app.get("/run", response_class=HTMLResponse)
def run(
    url: str = Query(...),
    analyst_name: str = Query(""),
    skip_analysis: bool = Query(False),
) -> str:
    label = analyst_name.strip() or "(unlabeled — for display only)"
    try:
        result = run_pipeline(url, analyst_name=label, skip_analysis=skip_analysis)
    except SourceFetchError as exc:
        return _render_form(error=str(exc))
    except AnthropicNotConfiguredError as exc:
        return _render_form(error=str(exc))

    settings = get_settings()
    models = {
        "claim_finder_model": settings.claim_finder_model,
        "stance_extractor_model": settings.stance_extractor_model,
        "claim_analyzer_model": settings.claim_analyzer_model,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = OUTPUT_DIR / f"{_slugify(result.source.title)}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
    nav_html = f'<div class="nav"><a href="/">← New run</a> &nbsp;·&nbsp; saved to <span class="mono">{html.escape(str(saved_path.relative_to(Path.cwd()) if saved_path.is_relative_to(Path.cwd()) else saved_path))}</span></div>'

    report_html = render_report(
        source=result.source,
        checked_claims=result.checked_claims,
        checked_stances=result.checked_stances,
        analyst_name=label,
        models=models,
        run_log=result.run_log,
        nav_html=nav_html,
    )
    saved_path.write_text(report_html, encoding="utf-8")
    return report_html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"AnalystAudit pipeline preview: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
