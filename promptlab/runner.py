"""Background execution of one lab run, and the in-memory status the UI polls.

Two modes:

- **raw** (the default): each selected pass is a plain Claude call with no `output_format`, and
  the lab shows exactly what came back. This is the mode to use while a prompt is being
  redesigned, because a structured call would refit the answer to the schema in
  `app/llm/schemas.py` and hide the change. See rawrun.py.
- **pipeline**: the real `run_pipeline`, schema-constrained, including ticker resolution, price
  data, stance snapshots and the claim analyzer. Use it once the schema matches the prompt again.

A run takes anywhere from ~30 seconds to several minutes (the claim analyzer runs once per due
claim, each with web search), so runs happen on a worker thread and the browser polls
`/api/runs/<id>` for progress. Status lives in this process only; the durable record is what
`runlog.write_run` puts on disk when the run finishes.
"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime, timezone
from typing import Any

import bootstrap  # noqa: F401  -- sys.path/env setup; must import before app.*

import runlog
from app.config import get_settings
from app.llm.schemas import ClaimExtraction
from app.sources.fetcher import SourceFetchError, fetch_source
from preview_pipeline import PromptOverrides, render_report, run_pipeline
from rawrun import RAW_PASSES, run_raw_pass
from store import PASS_IDS, cache_source, cached_source, pass_registry

_runs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _update(run_id: str, **fields: Any) -> None:
    with _lock:
        _runs[run_id].update(fields)


def _append_step(run_id: str, message: str) -> None:
    with _lock:
        _runs[run_id]["steps"].append({"at": _now(), "message": message})


def get_status(run_id: str) -> dict[str, Any] | None:
    with _lock:
        state = _runs.get(run_id)
        return dict(state) if state else None


def active_run_id() -> str | None:
    """The lab is single-user by design; the UI uses this to reattach to a run still going after
    a page reload."""
    with _lock:
        for run_id, state in _runs.items():
            if state["state"] == "running":
                return run_id
    return None


def _resolve_pass_config(requested: dict[str, Any], pass_ids: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Fill in the code's own prompt/model for any pass the UI didn't send, so a partial payload
    still runs the real thing for the rest."""
    registry = pass_registry()
    config: dict[str, dict[str, str]] = {}
    for pass_id in pass_ids:
        supplied = requested.get(pass_id) or {}
        prompt = (supplied.get("prompt") or "").strip() or registry[pass_id]["default_prompt"]
        model = (supplied.get("model") or "").strip() or registry[pass_id]["default_model"]
        config[pass_id] = {
            "prompt": prompt,
            "model": model,
            "version_name": supplied.get("version_name") or "",
        }
    return config


def start_run(
    *,
    url: str,
    analyst_name: str,
    mode: str,
    selected_passes: list[str],
    skip_analysis: bool,
    use_cache: bool,
    passes: dict[str, Any],
    pinned_claims_run_id: str | None = None,
) -> str:
    run_id = runlog.new_run_id(url or pinned_claims_run_id or "run")
    if mode == "raw":
        chosen = tuple(p for p in selected_passes if p in RAW_PASSES) or ("claim_finder",)
    else:
        chosen = PASS_IDS
    pass_config = _resolve_pass_config(passes, chosen)
    registry = pass_registry()
    with _lock:
        _runs[run_id] = {
            "run_id": run_id,
            "state": "running",
            "mode": mode,
            "url": url,
            "analyst_name": analyst_name,
            "skip_analysis": skip_analysis,
            "pinned_claims_run_id": pinned_claims_run_id,
            "started_at": _now(),
            "steps": [],
            "error": None,
            "record": None,
            "files": None,
            "modified_passes": [
                pass_id
                for pass_id, config in pass_config.items()
                if config["prompt"].strip() != registry[pass_id]["default_prompt"].strip()
            ],
        }

    threading.Thread(
        target=_execute,
        kwargs={
            "run_id": run_id,
            "url": url,
            "analyst_name": analyst_name,
            "mode": mode,
            "skip_analysis": skip_analysis,
            "use_cache": use_cache,
            "pass_config": pass_config,
            "pinned_claims_run_id": pinned_claims_run_id,
        },
        daemon=True,
    ).start()
    return run_id


def _load_source(run_id: str, url: str, use_cache: bool, step) -> tuple[Any, bool]:
    cached = cached_source(url) if use_cache else None
    if cached is not None:
        step(f"Using cached source text for {url}")
        return cached, True
    step(f"Fetching source: {url}")
    source = fetch_source(url)
    cache_source(url, source)
    return source, False


def _execute(
    *,
    run_id: str,
    url: str,
    analyst_name: str,
    mode: str,
    skip_analysis: bool,
    use_cache: bool,
    pass_config: dict[str, dict[str, str]],
    pinned_claims_run_id: str | None = None,
) -> None:
    started_at = _now()
    log: list[str] = []

    def step(message: str) -> None:
        log.append(message)
        _append_step(run_id, message)

    try:
        if mode == "raw":
            _execute_raw(
                run_id=run_id, url=url, analyst_name=analyst_name, use_cache=use_cache,
                pass_config=pass_config, started_at=started_at, log=log, step=step,
            )
        else:
            _execute_pipeline(
                run_id=run_id, url=url, analyst_name=analyst_name, skip_analysis=skip_analysis,
                use_cache=use_cache, pass_config=pass_config, started_at=started_at, step=step,
                pinned_claims_run_id=pinned_claims_run_id,
            )
    except SourceFetchError as exc:
        _update(run_id, state="error", error=f"Could not fetch that URL: {exc}", finished_at=_now())
    except Exception as exc:  # noqa: BLE001 -- surfaced to the UI verbatim; this is a local tool
        _update(
            run_id,
            state="error",
            error=f"{type(exc).__name__}: {exc}",
            traceback=traceback.format_exc(),
            finished_at=_now(),
        )


def _execute_raw(*, run_id, url, analyst_name, use_cache, pass_config, started_at, log, step) -> None:
    source, from_cache = _load_source(run_id, url, use_cache, step)
    step(f'"{source.title}" ({source.type}, published {source.published_at or "unknown"}, {len(source.content):,} chars)')

    today = datetime.now(timezone.utc).date()
    results = []
    for pass_id, config in pass_config.items():
        step(f"Running {pass_id} with no output schema...")
        result = run_raw_pass(
            pass_id=pass_id, system_prompt=config["prompt"], model=config["model"],
            source=source, today=today,
        )
        results.append(result)
        if result.error:
            step(f"{pass_id} failed: {result.error}")
        else:
            step(f"{pass_id} returned {len(result.completion.text):,} chars")

    record = runlog.build_raw_record(
        run_id=run_id, url=url, analyst_name=analyst_name, used_cached_source=from_cache,
        pass_config=pass_config, source=source, results=results, run_log=log,
        started_at=started_at, finished_at=_now(),
    )
    files = runlog.write_run(record=record, source_text=source.content)
    step(f"Saved run to {files['dir']}")
    _update(run_id, state="done", record=record, files=files, finished_at=_now())


def _execute_pipeline(*, run_id, url, analyst_name, skip_analysis, use_cache, pass_config, started_at, step, pinned_claims_run_id=None) -> None:
    prefetched_claims = None
    if pinned_claims_run_id:
        pin = runlog.pinned_claims_from_run(pinned_claims_run_id)
        if pin is None:
            raise ValueError(
                f"Run {pinned_claims_run_id} has no pinnable claims (missing, not a pipeline "
                "run, or extracted zero claims)."
            )
        url = pin["url"]
        prefetched_claims = [ClaimExtraction.model_validate(c) for c in pin["claims"]]
        step(f"Pinning {len(prefetched_claims)} claim(s) from run {pinned_claims_run_id} ({pin['title']})")

    prefetched_source = cached_source(url) if use_cache else None
    overrides = PromptOverrides(
        claim_finder_system=pass_config["claim_finder"]["prompt"],
        claim_finder_model=pass_config["claim_finder"]["model"],
        stance_extractor_system=pass_config["stance_extractor"]["prompt"],
        stance_extractor_model=pass_config["stance_extractor"]["model"],
        claim_analyzer_system=pass_config["claim_analyzer"]["prompt"],
        claim_analyzer_model=pass_config["claim_analyzer"]["model"],
    )
    result = run_pipeline(
        url,
        analyst_name=analyst_name,
        skip_analysis=skip_analysis,
        on_step=step,
        overrides=overrides,
        prefetched_source=prefetched_source,
        prefetched_claims=prefetched_claims,
    )
    if prefetched_source is None:
        cache_source(url, result.source)

    record = runlog.build_pipeline_record(
        run_id=run_id, url=url, analyst_name=analyst_name, skip_analysis=skip_analysis,
        used_cached_source=prefetched_source is not None, pass_config=pass_config, result=result,
        started_at=started_at, finished_at=_now(), pinned_from_run_id=pinned_claims_run_id,
    )
    settings = get_settings()
    report_html = render_report(
        source=result.source,
        checked_claims=result.checked_claims,
        checked_stances=result.checked_stances,
        analyst_name=analyst_name,
        models={
            "claim_finder_model": pass_config["claim_finder"]["model"],
            "stance_extractor_model": pass_config["stance_extractor"]["model"],
            "claim_analyzer_model": pass_config["claim_analyzer"]["model"],
        },
        run_log=result.run_log,
        nav_html=f'<div class="nav">Prompt lab run <span class="mono">{run_id}</span>'
        f' &nbsp;·&nbsp; meta-analyst model in config: {settings.meta_analyst_model}</div>',
    )
    files = runlog.write_run(record=record, source_text=result.source.content, report_html=report_html)
    step(f"Saved run to {files['dir']}")
    _update(run_id, state="done", record=record, files=files, finished_at=_now())
