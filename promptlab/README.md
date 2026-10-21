# Prompt lab

A local web app for iterating on AnalystAudit's system prompts. Edit a pass's prompt in the
browser, run it against a real YouTube video or blog post, read what came out, and hand the
saved log to Claude Code for the next round of edits.

```bash
cd promptlab && ./run.sh          # http://127.0.0.1:8020
./run.sh --port 8030              # any server.py flag passes through
```

Needs `ANTHROPIC_API_KEY` in `backend/.env` (loaded automatically) and the backend's virtualenv
at `backend/.venv`. The prompt lab currently runs through the same Anthropic-only client as the
backend; `HUGGINGFACE_API_KEY` is reserved for the planned provider migration and is not used.
Port 8020 keeps it clear of the real app (8000/5173) and
`backend/scripts/preview_server.py` (8010), so they can all run at once.

## What it is, and what it deliberately isn't

It's a **separate app** with its own server, port, and storage, but it is **not a separate
pipeline**. It imports `run_pipeline` from `backend/scripts/preview_pipeline.py`, which calls the
real `app/llm/*` passes, so an experiment here exercises the same code path the CLI preview and
the eventual production jobs do. The only difference is that each pass's `system_prompt` and
`model` arguments get filled in from the editor instead of being left null.

Nothing is written to the database. Editing a prompt in the browser does **not** write back to
`app/llm/*.py`. Once an edit is worth keeping, it gets copied into the source file by hand (or
by Claude Code), which is the point of keeping the runs as files.

It's distinct from `backend/scripts/preview_server.py`, which runs the committed prompts with no
way to change them: that one answers "what does the pipeline do with this video," this one
answers "what happens if the prompt says it differently."

## The three editable passes

| Tab | Pass | Cost per run |
|---|---|---|
| Claim finder | `app/llm/claim_finder.py` | one call |
| Stance extractor | `app/llm/stance_extractor.py` | one call |
| Claim analyzer | `app/llm/claim_analyzer.py` | one call **per due claim**, each with web search |

"Skip claim analyzer" is checked by default for that reason: iterating on claim finder or the
stance extractor is much faster and cheaper with it off. Uncheck it when the analyzer prompt is
what you're working on. Meta-analyst (stage 3) isn't in the lab: it reads a whole stored claim
history, which doesn't exist yet.

Each tab shows a dot when its prompt differs from the one in code, and "Reset to code" reloads
the committed version. Model is per-pass, same as `app/config.py`. The model selector currently
only changes the model ID sent through Anthropic; it is not a Hugging Face adapter. Do not assume
that entering a Hugging Face model ID will work until the provider-neutral LLM client is added.

**Saved versions** (`prompts/<pass>/<name>.json`) are named working drafts, saved to disk and
loadable from the dropdown; saving over a name overwrites it. Unsaved edits survive a page
reload via localStorage. Neither is a history. `runs/` is, since every run records the exact
prompt text it used.

**Source cache**: the fetched transcript/article is cached per URL under `cache/`, because
refetching it between prompt edits is the slowest non-LLM part of a run and it never changes.
Uncheck "Use cached source" or hit "Clear source cache" to refetch.

## Bringing a run into Claude Code

Every run writes `runs/<run-id>/`:

| File | What it's for |
|---|---|
| `run.md` | **The one to hand to Claude.** Full prompt text used, a unified diff against the prompt in code, every claim and stance with its supporting quotes, the analyzer's verdicts, the run log, and an empty review-notes section at the end. |
| `run.json` | The same content structured, for diffing two runs programmatically. |
| `source.txt` | The raw transcript/article the passes saw, kept out of `run.md` so it stays readable, but there for checking whether a quote was real. |
| `report.html` | The styled report `preview_pipeline.py` already renders, in the app's own design language. |

`runs/latest.md` is a copy of the newest `run.md`, so `read promptlab/runs/latest.md` always
works without looking up an id. `runs/index.json` backs the "Past runs" tab.

The results pane's "Copy the ask" button hands you a ready-made prompt naming the right file.
The typical loop is: run, skim the output, then

```
read promptlab/runs/latest.md and tell me why claim 4's target window is wrong
```

and once an edit earns its place, ask for it to be written into `app/llm/claim_finder.py` so the
committed prompt and the lab's "reset to code" default move together.

`runs/` and `cache/` are gitignored (transcripts and per-run logs pile up); `prompts/` is not,
so a named draft can be committed if it's worth keeping.

## The seam this depends on

`extract_claims`, `extract_stances`, `resolve_claim`, and `analyze_analyst` each take optional
`system_prompt` and `model` arguments that override the module constant and `app/config.py`.
Production callers leave both null and behave exactly as before. `PromptOverrides` in
`preview_pipeline.py` is what threads them through a whole run, alongside `prefetched_source`
for the cache. That's the entire footprint of the lab inside the real backend.
