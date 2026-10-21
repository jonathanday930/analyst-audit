"""Everything the prompt lab keeps on disk: the pass registry (what's editable and what the
code's current default is), saved prompt versions, and the fetched-source cache.

Nothing here touches the real database: the lab is a testing tool, same scope as
`backend/scripts/preview_*.py`. Saved prompt versions are plain JSON files under `prompts/` so
they can be read, diffed, and committed like any other file; the source cache under `cache/` is
throwaway and gitignored.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import bootstrap  # noqa: F401  -- sys.path/env setup; must import before app.*

from app.config import get_settings
from app.sources.fetcher import FetchedSource
from bootstrap import CACHE_DIR, PROMPTS_DIR
from preview_pipeline import DEFAULT_PROMPTS

# Models worth reaching for from the lab. The pipeline's own default is claude-sonnet-5 for
# every pass (see CLAUDE.md's Model choice). The cheaper entries are here so a prompt that's
# already validated on Sonnet can be re-tested on a smaller model without editing config.py.
MODEL_CHOICES = [
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
]


def _pass_registry() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    return {
        "claim_finder": {
            "label": "Claim finder",
            "blurb": "Stage 1a. Pulls every distinct falsifiable claim out of the source. "
            "Adaptive thinking on, no tools.",
            "module": "backend/src/app/llm/claim_finder.py",
            "supports_raw": True,
            "default_prompt": DEFAULT_PROMPTS["claim_finder"],
            "default_model": settings.claim_finder_model,
        },
        "stance_extractor": {
            "label": "Stance extractor",
            "blurb": "Stage 1b. Pulls disclosed positions and loose sentiment out of the same "
            "text. Thinking off, no tools.",
            "module": "backend/src/app/llm/stance_extractor.py",
            "supports_raw": True,
            "default_prompt": DEFAULT_PROMPTS["stance_extractor"],
            "default_model": settings.stance_extractor_model,
        },
        "claim_analyzer": {
            "label": "Claim analyzer",
            "blurb": "Stage 2. Grades one due claim against real price data plus web search. "
            "Runs once per due claim, so edits here cost the most per run.",
            "module": "backend/src/app/llm/claim_analyzer.py",
            # Its user turn is built from one already-extracted claim, which raw mode has no
            # way to produce: pipeline mode only. See rawrun.py.
            "supports_raw": False,
            "default_prompt": DEFAULT_PROMPTS["claim_analyzer"],
            "default_model": settings.claim_analyzer_model,
        },
    }


def pass_registry() -> dict[str, dict[str, Any]]:
    """Rebuilt on each call rather than cached at import: the defaults it reports are the live
    contents of the code, so editing a prompt in `app/llm/` and restarting picks it up."""
    return _pass_registry()


PASS_IDS = ("claim_finder", "stance_extractor", "claim_analyzer")


# --- saved prompt versions -------------------------------------------------------------------


def slugify(text: str, *, fallback: str = "untitled", limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit] or fallback


def _version_path(pass_id: str, version_id: str) -> Path:
    return PROMPTS_DIR / pass_id / f"{version_id}.json"


def list_versions(pass_id: str | None = None) -> list[dict[str, Any]]:
    """Metadata only, no prompt bodies. This feeds the version dropdown, which doesn't need them,
    and a lab with many saved versions would otherwise ship a lot of text per page load."""
    ids = [pass_id] if pass_id else list(PASS_IDS)
    out: list[dict[str, Any]] = []
    for pid in ids:
        directory = PROMPTS_DIR / pid
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            out.append(
                {
                    "id": data.get("id", path.stem),
                    "pass_id": pid,
                    "name": data.get("name", path.stem),
                    "model": data.get("model"),
                    "saved_at": data.get("saved_at"),
                    "note": data.get("note", ""),
                    "path": str(path),
                }
            )
    out.sort(key=lambda item: item.get("saved_at") or "", reverse=True)
    return out


def get_version(pass_id: str, version_id: str) -> dict[str, Any] | None:
    path = _version_path(pass_id, version_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_version(*, pass_id: str, name: str, prompt: str, model: str, note: str = "") -> dict[str, Any]:
    """Saving under an existing name overwrites it: versions are named working drafts, not an
    append-only history. The append-only record is `runs/`, where every run stores the exact
    prompt text it used, so nothing is ever actually lost by overwriting a draft here."""
    if pass_id not in PASS_IDS:
        raise ValueError(f"unknown pass: {pass_id}")
    version_id = slugify(name, fallback="draft")
    record = {
        "id": version_id,
        "pass_id": pass_id,
        "name": name.strip() or version_id,
        "model": model,
        "note": note,
        "prompt": prompt,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = _version_path(pass_id, version_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def delete_version(pass_id: str, version_id: str) -> bool:
    path = _version_path(pass_id, version_id)
    if not path.is_file():
        return False
    path.unlink()
    return True


# --- fetched-source cache --------------------------------------------------------------------

_SOURCE_CACHE_DIR = CACHE_DIR / "sources"


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:20]


def cached_source(url: str) -> FetchedSource | None:
    """Transcript + metadata fetching is the slowest non-LLM part of a run and never changes
    between prompt edits, so the lab caches it per URL. Cleared by deleting `cache/sources/`."""
    path = _SOURCE_CACHE_DIR / f"{_cache_key(url)}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    published = data.get("published_at")
    data["published_at"] = date.fromisoformat(published) if published else None
    return FetchedSource(**data)


def cache_source(url: str, source: FetchedSource) -> None:
    _SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = asdict(source)
    data["published_at"] = source.published_at.isoformat() if source.published_at else None
    path = _SOURCE_CACHE_DIR / f"{_cache_key(url)}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_source_cache() -> int:
    if not _SOURCE_CACHE_DIR.is_dir():
        return 0
    paths = list(_SOURCE_CACHE_DIR.glob("*.json"))
    for path in paths:
        path.unlink()
    return len(paths)
