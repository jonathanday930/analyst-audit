#!/usr/bin/env python3
"""AnalystAudit prompt lab: a local web app for iterating on the pipeline's system prompts.

Edit a pass's system prompt in the browser, run it against a real YouTube video or blog post,
read the output, and get a file path you can hand straight to Claude Code for the next round of
edits. Every run is written to `promptlab/runs/<run-id>/` (see runlog.py for what's in there).

This is a separate app from the real backend on purpose. It imports the real pipeline
(`app/llm/*` via `backend/scripts/preview_pipeline.py`) rather than copying it, but it has its
own server, port, and storage, and it never writes to the database. Distinct from
`backend/scripts/preview_server.py`, which runs the committed prompts with no way to edit them.

Usage:
    cd promptlab && ../backend/.venv/bin/python server.py     # http://127.0.0.1:8020
    ../backend/.venv/bin/python server.py --port 8030

Requires ANTHROPIC_API_KEY in backend/.env (loaded automatically) and network access. The lab
currently uses the Anthropic-only LLM client; HUGGINGFACE_API_KEY is reserved for the planned
provider migration and entering a Hugging Face model ID does not activate that provider.
"""

from __future__ import annotations

import argparse
from typing import Any

import bootstrap  # noqa: F401  -- sys.path/env setup; must import before app.*

import runlog
import runner
import store
import uvicorn
from bootstrap import PROJECT_ROOT, STATIC_DIR
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="AnalystAudit prompt lab")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/bootstrap")
def api_bootstrap() -> dict[str, Any]:
    """One call that gives the UI everything it needs to draw itself: the editable passes with
    the prompt text currently in code, the model menu, saved versions, and past runs."""
    registry = store.pass_registry()
    return {
        "passes": [
            {
                "id": pass_id,
                "label": data["label"],
                "blurb": data["blurb"],
                "module": data["module"],
                "default_prompt": data["default_prompt"],
                "default_model": data["default_model"],
                "supports_raw": data["supports_raw"],
            }
            for pass_id, data in registry.items()
        ],
        "models": store.MODEL_CHOICES,
        "versions": store.list_versions(),
        "runs": runlog.load_index()[:40],
        "active_run_id": runner.active_run_id(),
        "project_root": str(PROJECT_ROOT),
    }


@app.get("/api/versions/{pass_id}/{version_id}")
def api_get_version(pass_id: str, version_id: str) -> dict[str, Any]:
    version = store.get_version(pass_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="No saved version with that id.")
    return version


@app.post("/api/versions")
def api_save_version(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the version a name.")
    try:
        record = store.save_version(
            pass_id=payload.get("pass_id", ""),
            name=name,
            prompt=payload.get("prompt", ""),
            model=payload.get("model", ""),
            note=(payload.get("note") or "").strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"saved": record, "versions": store.list_versions()}


@app.delete("/api/versions/{pass_id}/{version_id}")
def api_delete_version(pass_id: str, version_id: str) -> dict[str, Any]:
    if not store.delete_version(pass_id, version_id):
        raise HTTPException(status_code=404, detail="No saved version with that id.")
    return {"versions": store.list_versions()}


@app.post("/api/runs")
def api_start_run(payload: dict[str, Any] = Body(...)) -> dict[str, str]:
    pinned_claims_run_id = (payload.get("pinned_claims_run_id") or "").strip() or None
    url = (payload.get("url") or "").strip()
    if not url and not pinned_claims_run_id:
        raise HTTPException(status_code=400, detail="Paste a video or blog URL first.")
    if runner.active_run_id():
        raise HTTPException(status_code=409, detail="A run is already in progress.")
    mode = payload.get("mode") or "raw"
    if mode not in {"raw", "pipeline"}:
        raise HTTPException(status_code=400, detail="mode must be 'raw' or 'pipeline'.")
    if pinned_claims_run_id and mode != "pipeline":
        raise HTTPException(status_code=400, detail="Pinned claims require pipeline mode.")
    if pinned_claims_run_id and runlog.pinned_claims_from_run(pinned_claims_run_id) is None:
        raise HTTPException(status_code=400, detail=f"Run {pinned_claims_run_id} has no pinnable claims.")
    run_id = runner.start_run(
        url=url,
        analyst_name=(payload.get("analyst_name") or "").strip() or "(unlabeled)",
        mode=mode,
        selected_passes=payload.get("selected_passes") or ["claim_finder"],
        skip_analysis=bool(payload.get("skip_analysis")),
        use_cache=payload.get("use_cache", True) is not False,
        passes=payload.get("passes") or {},
        pinned_claims_run_id=pinned_claims_run_id,
    )
    return {"run_id": run_id}


@app.get("/api/runs")
def api_list_runs() -> dict[str, Any]:
    return {"runs": runlog.load_index()[:40]}


@app.get("/api/runs/{run_id}")
def api_run_status(run_id: str) -> dict[str, Any]:
    """Serves an in-flight run from memory and a finished one from disk, so a past run reloads
    the same way a fresh one arrives."""
    status = runner.get_status(run_id)
    if status is not None:
        return status
    record = runlog.load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No run with that id.")
    files = {
        "dir": f"promptlab/runs/{run_id}",
        "markdown": f"promptlab/runs/{run_id}/run.md",
        "json": f"promptlab/runs/{run_id}/run.json",
        "source": f"promptlab/runs/{run_id}/source.txt",
        "latest": "promptlab/runs/latest.md",
    }
    if (bootstrap.RUNS_DIR / run_id / "report.html").is_file():
        files["html"] = f"promptlab/runs/{run_id}/report.html"
    return {
        "run_id": run_id,
        "state": "done",
        "mode": record.get("mode", "pipeline"),
        "url": record["url"],
        "analyst_name": record["analyst_name"],
        "skip_analysis": record.get("skip_analysis", False),
        "pinned_claims_run_id": record.get("pinned_from_run_id"),
        "started_at": record["started_at"],
        "finished_at": record["finished_at"],
        "steps": [{"at": "", "message": step} for step in record["run_log"]],
        "error": None,
        "record": record,
        "files": files,
        "modified_passes": [pid for pid, data in record["passes"].items() if data["modified"]],
    }


@app.get("/api/runs/{run_id}/report", response_class=FileResponse)
def api_run_report(run_id: str) -> FileResponse:
    path = bootstrap.RUNS_DIR / run_id / "report.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No rendered report for that run.")
    return FileResponse(path, media_type="text/html")


@app.get("/api/runs/{run_id}/markdown", response_class=PlainTextResponse)
def api_run_markdown(run_id: str) -> PlainTextResponse:
    """The exact text of run.md, so the UI can show it and offer a one-click copy for pasting
    into a Claude Code session that isn't running in this repo."""
    path = bootstrap.RUNS_DIR / run_id / "run.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No markdown digest for that run.")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.post("/api/cache/clear")
def api_clear_cache() -> dict[str, int]:
    return {"cleared": store.clear_source_cache()}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(HTTPException)
def _http_error(_request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8020, help="Default 8020, clear of the real app (8000/5173) and preview_server (8010).")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"AnalystAudit prompt lab: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
