"""Writes each run to disk in a form that's useful to paste (or point Claude Code) at.

Every run gets its own directory under `runs/<run-id>/` holding four things:

- `run.md`:     the digest. Full prompt text used, a unified diff against the prompt currently
                in the code, and the pass output. This is the file to hand to Claude Code.
- `run.json`:   the same thing structured, for programmatic diffing between two runs.
- `source.txt`: the transcript/article text the passes saw, kept out of run.md so the digest
                stays readable but available for checking a quote against the source.
- `report.html`: pipeline-mode runs also get the styled report
                `backend/scripts/preview_pipeline.py` renders.

Nothing here knows the shape of a claim or a stance. Raw-mode output is written verbatim and
pipeline-mode output is dumped as JSON, so a prompt (and schema) redesign changes what these
files say without needing a change here.

`runs/index.json` is the browsable list, and `runs/latest.md` is a copy of the newest run.md so
"read promptlab/runs/latest.md" always works without looking up an id.
"""

from __future__ import annotations

import difflib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import bootstrap  # noqa: F401  -- sys.path/env setup; must import before app.*

from bootstrap import PROJECT_ROOT, RUNS_DIR
from preview_pipeline import CheckedClaim, CheckedStance, PipelineResult
from rawrun import RawPassResult
from store import pass_registry, slugify

INDEX_PATH = RUNS_DIR / "index.json"
LATEST_PATH = RUNS_DIR / "latest.md"


def new_run_id(url: str) -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slugify(url.rsplit('/', 1)[-1], fallback='run', limit=24)}"


def _rel(path: Path) -> str:
    """Paths in run.md are relative to the repo root so they can be pasted into a Claude Code
    session started anywhere in the project."""
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def _prompt_diff(default: str, used: str, pass_id: str) -> str:
    # Both prompts are module constants written without a trailing newline; normalising that
    # keeps difflib from gluing the last unchanged line onto the first added one.
    return "".join(
        difflib.unified_diff(
            (default.rstrip("\n") + "\n").splitlines(keepends=True),
            (used.rstrip("\n") + "\n").splitlines(keepends=True),
            fromfile=f"{pass_id} (in code)",
            tofile=f"{pass_id} (this run)",
            n=2,
        )
    )


def _pass_block(pass_config: dict[str, dict[str, str]]) -> dict[str, Any]:
    registry = pass_registry()
    passes: dict[str, Any] = {}
    for pass_id, config in pass_config.items():
        default_prompt = registry[pass_id]["default_prompt"]
        used_prompt = config["prompt"]
        passes[pass_id] = {
            "label": registry[pass_id]["label"],
            "module": registry[pass_id]["module"],
            "model": config["model"],
            "default_model": registry[pass_id]["default_model"],
            "prompt": used_prompt,
            "modified": used_prompt.strip() != default_prompt.strip(),
            "diff_vs_code": _prompt_diff(default_prompt, used_prompt, pass_id),
            "version_name": config.get("version_name") or None,
        }
    return passes


def _source_block(source: Any) -> dict[str, Any]:
    return {
        "type": source.type,
        "title": source.title,
        "canonical_url": source.canonical_url,
        "published_at": source.published_at.isoformat() if source.published_at else None,
        "char_count": len(source.content),
        "youtube_channel_id": source.youtube_channel_id,
        "blog_domain": source.blog_domain,
    }


# --- structured records ------------------------------------------------------------------


def build_raw_record(
    *,
    run_id: str,
    url: str,
    analyst_name: str,
    used_cached_source: bool,
    pass_config: dict[str, dict[str, str]],
    source: Any,
    results: list[RawPassResult],
    run_log: list[str],
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": "raw",
        "started_at": started_at,
        "finished_at": finished_at,
        "url": url,
        "analyst_name": analyst_name,
        "used_cached_source": used_cached_source,
        "source": _source_block(source),
        "passes": _pass_block(pass_config),
        "raw_results": [
            {
                "pass_id": result.pass_id,
                "model": result.model,
                "user_content_preview": result.user_content_preview,
                "error": result.error,
                "text": result.completion.text if result.completion else None,
                "thinking": result.completion.thinking if result.completion else None,
                "stop_reason": result.completion.stop_reason if result.completion else None,
                "input_tokens": result.completion.input_tokens if result.completion else None,
                "output_tokens": result.completion.output_tokens if result.completion else None,
            }
            for result in results
        ],
        "run_log": run_log,
    }


def build_pipeline_record(
    *,
    run_id: str,
    url: str,
    analyst_name: str,
    skip_analysis: bool,
    used_cached_source: bool,
    pass_config: dict[str, dict[str, str]],
    result: PipelineResult,
    started_at: str,
    finished_at: str,
    pinned_from_run_id: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": "pipeline",
        "started_at": started_at,
        "finished_at": finished_at,
        "url": url,
        "analyst_name": analyst_name,
        "skip_analysis": skip_analysis,
        "used_cached_source": used_cached_source,
        "pinned_from_run_id": pinned_from_run_id,
        "source": _source_block(result.source),
        "passes": _pass_block(pass_config),
        "claims": [_claim_record(c) for c in result.checked_claims],
        "stances": [_stance_record(s) for s in result.checked_stances],
        "run_log": result.run_log,
    }


def _claim_record(checked: CheckedClaim) -> dict[str, Any]:
    return {
        "claim": checked.claim.model_dump(mode="json"),
        "resolution": checked.resolution.model_dump(mode="json") if checked.resolution else None,
        "used_web_search": checked.used_web_search,
        "skip_reason": checked.skip_reason,
        "benchmark_ticker": checked.benchmark_ticker,
    }


def _stance_record(checked: CheckedStance) -> dict[str, Any]:
    return {
        "stance": checked.stance.model_dump(mode="json"),
        "snapshot": checked.snapshot.model_dump(mode="json") if checked.snapshot else None,
        "skip_reason": checked.skip_reason,
    }


# --- markdown digest ---------------------------------------------------------------------


def _prompt_sections(record: dict[str, Any]) -> list[str]:
    lines = ["## Prompts used", ""]
    for data in record["passes"].values():
        status = "EDITED" if data["modified"] else "unchanged from code"
        version = f" (saved version: {data['version_name']})" if data["version_name"] else ""
        lines += [
            f"### {data['label']}: {status}{version}",
            "",
            f"- Model: `{data['model']}` (code default: `{data['default_model']}`)",
            f"- Lives in: `{data['module']}`",
            "",
        ]
        if data["modified"]:
            lines += ["Diff against the prompt currently in code:", "", "```diff",
                      data["diff_vs_code"].rstrip(), "```", ""]
        lines += ["<details><summary>Full system prompt as run</summary>", "", "```text",
                  data["prompt"].rstrip(), "```", "", "</details>", ""]
    return lines


def _header(record: dict[str, Any], source_path: Path) -> list[str]:
    source = record["source"]
    modified = [pid for pid, data in record["passes"].items() if data["modified"]]
    return [
        f"# Prompt lab run: {source['title']}",
        "",
        f"One AnalystAudit pipeline run in **{record['mode']} mode** (`promptlab/`, a testing "
        "tool; nothing here was written to the database).",
        "",
        "## Run",
        "",
        f"- **Run id:** `{record['run_id']}`",
        f"- **Started / finished:** {record['started_at']} / {record['finished_at']}",
        f"- **Source:** {record['url']}",
        f"- **Type / published:** {source['type']} / {source['published_at'] or 'unknown'}",
        f"- **Analyst label:** {record['analyst_name']}",
    ] + ([f"- **Claims pinned from run:** `{record['pinned_from_run_id']}` (claim finder did not run this pass)"]
         if record.get("pinned_from_run_id") else []) + [
        f"- **Source text:** `{_rel(source_path)}` ({source['char_count']:,} chars"
        + (", from cache" if record["used_cached_source"] else "")
        + ")",
        f"- **Prompts edited vs. code:** {', '.join(modified) if modified else 'none, every pass ran the committed prompt'}",
    ]


def _raw_body(record: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "> Raw mode: no `output_format` was set on these calls, so the text below is exactly "
        "what the model wrote. It has not been fitted to `app/llm/schemas.py`.",
        "",
    ]
    for result in record["raw_results"]:
        label = record["passes"][result["pass_id"]]["label"]
        lines += [f"## {label}: raw output", ""]
        if result["error"]:
            lines += [f"**The call failed:** {result['error']}", ""]
            continue
        tokens = []
        if result["input_tokens"] is not None:
            tokens.append(f"{result['input_tokens']:,} in")
        if result["output_tokens"] is not None:
            tokens.append(f"{result['output_tokens']:,} out")
        meta = f"`{result['model']}`"
        if tokens:
            meta += f" · {' / '.join(tokens)} tokens"
        if result["stop_reason"]:
            meta += f" · stop_reason `{result['stop_reason']}`"
        lines += [meta, ""]
        if result["thinking"]:
            lines += ["<details><summary>Model's thinking</summary>", "", "```text",
                      result["thinking"].rstrip(), "```", "", "</details>", ""]
        lines += ["```text", (result["text"] or "(the model returned no text)").rstrip(), "```", ""]
    return lines


def _pipeline_body(record: dict[str, Any]) -> list[str]:
    """Deliberately dumps whatever fields the schema produced rather than naming any of them:
    the claim schema is expected to change, and a digest that hardcodes field names would
    either break or quietly omit the new ones."""
    lines = [
        "",
        "> Pipeline mode: these objects were fitted to the schemas in `app/llm/schemas.py`. "
        "Fields a prompt asks for that the schema does not define are dropped by the "
        "structured-output call and will not appear here.",
        "",
        f"## Claims ({len(record['claims'])})",
        "",
    ]
    if record["claims"]:
        for index, entry in enumerate(record["claims"], start=1):
            lines += [f"### Claim {index}", "", "```json",
                      json.dumps(entry["claim"], indent=2, ensure_ascii=False), "```", ""]
            if entry.get("resolution"):
                lines += ["Analyzer result:", "", "```json",
                          json.dumps(entry["resolution"], indent=2, ensure_ascii=False), "```",
                          f"(web search used: {'yes' if entry['used_web_search'] else 'no'})", ""]
            elif entry.get("skip_reason"):
                lines += [f"Analyzer: not run. {entry['skip_reason']}", ""]
    else:
        lines += ["_Nothing extracted._", ""]

    lines += [f"## Stances ({len(record['stances'])})", ""]
    if record["stances"]:
        for index, entry in enumerate(record["stances"], start=1):
            lines += [f"### Stance {index}", "", "```json",
                      json.dumps(entry["stance"], indent=2, ensure_ascii=False), "```", ""]
            if entry.get("snapshot"):
                lines += ["Market snapshot since the call:", "", "```json",
                          json.dumps(entry["snapshot"], indent=2, ensure_ascii=False), "```", ""]
            elif entry.get("skip_reason"):
                lines += [f"Market snapshot: {entry['skip_reason']}", ""]
    else:
        lines += ["_Nothing extracted._", ""]
    return lines


def render_markdown(record: dict[str, Any], *, source_path: Path) -> str:
    lines = _header(record, source_path)
    if record["mode"] == "raw":
        lines += _raw_body(record)
    else:
        lines.append(
            f"- **Claim analyzer:** {'skipped this run' if record['skip_analysis'] else 'ran on every due claim'}"
        )
        lines += _pipeline_body(record)
    lines += ["", *_prompt_sections(record)]
    lines += ["## Run log", ""]
    lines += [f"- {step}" for step in record["run_log"]]
    lines += [
        "",
        "## Review notes",
        "",
        "_Empty on purpose. Write what looked wrong here (or have Claude Code fill it in), so "
        "the next run has something to compare against._",
        "",
    ]
    return "\n".join(lines)


# --- writing -----------------------------------------------------------------------------


def write_run(*, record: dict[str, Any], source_text: str, report_html: str | None = None) -> dict[str, str]:
    run_dir = RUNS_DIR / record["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)

    source_path = run_dir / "source.txt"
    source_path.write_text(source_text, encoding="utf-8")

    json_path = run_dir / "run.json"
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    md_path = run_dir / "run.md"
    markdown = render_markdown(record, source_path=source_path)
    md_path.write_text(markdown, encoding="utf-8")
    LATEST_PATH.write_text(markdown, encoding="utf-8")

    files = {
        "dir": _rel(run_dir),
        "markdown": _rel(md_path),
        "json": _rel(json_path),
        "source": _rel(source_path),
        "latest": _rel(LATEST_PATH),
    }
    if report_html is not None:
        html_path = run_dir / "report.html"
        html_path.write_text(report_html, encoding="utf-8")
        files["html"] = _rel(html_path)

    _append_index(record)
    return files


def _summary_counts(record: dict[str, Any]) -> str:
    if record["mode"] == "raw":
        chars = sum(len(result["text"] or "") for result in record["raw_results"])
        return f"{len(record['raw_results'])} pass(es), {chars:,} chars of output"
    return f"{len(record['claims'])} claims, {len(record['stances'])} stances"


def _append_index(record: dict[str, Any]) -> None:
    entries = [entry for entry in load_index() if entry["run_id"] != record["run_id"]]
    entries.insert(
        0,
        {
            "run_id": record["run_id"],
            "mode": record["mode"],
            "started_at": record["started_at"],
            "url": record["url"],
            "title": record["source"]["title"],
            "analyst_name": record["analyst_name"],
            "summary": _summary_counts(record),
            "claim_count": len(record.get("claims", [])),
            "modified_passes": [pid for pid, data in record["passes"].items() if data["modified"]],
        },
    )
    INDEX_PATH.write_text(json.dumps(entries[:200], indent=2, ensure_ascii=False), encoding="utf-8")


def load_index() -> list[dict[str, Any]]:
    if not INDEX_PATH.is_file():
        return []
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def load_run(run_id: str) -> dict[str, Any] | None:
    path = RUNS_DIR / run_id / "run.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def pinned_claims_from_run(run_id: str) -> dict[str, Any] | None:
    """Pulls the claim-finder output back out of a past pipeline run, for a later run to reuse
    without re-extracting. Every pipeline run already stores each claim in the exact
    `ClaimExtraction`-shaped dict `run.json` needs (see `_claim_record`), so no separate storage
    is needed for this — a run IS a saved claim set. Returns None if the run doesn't exist, isn't
    a pipeline run, or extracted zero claims (nothing to pin)."""
    record = load_run(run_id)
    if record is None or record.get("mode") != "pipeline" or not record.get("claims"):
        return None
    return {
        "run_id": run_id,
        "url": record["url"],
        "title": record["source"]["title"],
        "claims": [entry["claim"] for entry in record["claims"]],
    }
