"""Import/env setup so this app can drive the real backend pipeline.

The prompt lab deliberately does not vendor a copy of the pipeline: it imports
`app.llm.*` and `preview_pipeline.run_pipeline` straight out of `../backend`, so an experiment
here always exercises the same code path the CLI preview and the eventual production jobs do.
That means putting the backend's `src/` and `scripts/` on `sys.path`, and loading
`backend/.env` (ANTHROPIC_API_KEY) into the environment before `app.config.get_settings()` is
first called: it resolves its env file relative to the working directory, which is this app's
directory, not the backend's.

Import this module before anything that touches `app.*` or `preview_pipeline`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

PROMPTLAB_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PROMPTLAB_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

PROMPTS_DIR = PROMPTLAB_DIR / "prompts"
RUNS_DIR = PROMPTLAB_DIR / "runs"
CACHE_DIR = PROMPTLAB_DIR / "cache"
STATIC_DIR = PROMPTLAB_DIR / "static"

for _path in (BACKEND_DIR / "scripts", BACKEND_DIR / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

load_dotenv(BACKEND_DIR / ".env")

for _dir in (PROMPTS_DIR, RUNS_DIR, CACHE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
