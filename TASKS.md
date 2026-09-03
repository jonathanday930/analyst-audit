# Tasks

Working backlog for Codex: flat, tagged, no grouped narrative. For architecture, schema, and
the rationale behind any task here, see `CLAUDE.md`; this file doesn't restate it. For the line
format and conventions (adding a task, completion records, archiving), see the top-level
`../CLAUDE.md`'s "Task files and completion records" section and `../AGENTS.md`'s versions of
the same, this file just follows them, it doesn't redefine them.

**Tags in use**: `backend`, `db`, `matching`, `infra`, `api`, `frontend`.

Once this file has a lot of completed entries, older ones get moved to `TASKS_ARCHIVE.md`
(same directory); check there too if you're looking for older history that isn't below.

- [ ] [backend] Scaffold `backend/` mirroring `../youtube_fact_checker/backend`'s layout: `pyproject.toml`, `src/app/` package, FastAPI entrypoint, `config.py` for env vars, `tests/`. — Requested: 2026-09-02 18:14 MDT
- [ ] [backend] Add `Dockerfile` and `fly.toml`, mirroring `../youtube_fact_checker`'s, adjusted for a persistent Postgres-backed app rather than a stateless one. — Requested: 2026-09-02 18:14 MDT
- [ ] [db] Provision Postgres as a Fly.io managed Postgres app attached to this app. — Requested: 2026-09-02 18:14 MDT
- [ ] [db] Set up SQLAlchemy with Alembic migrations. — Requested: 2026-09-02 18:14 MDT
- [ ] [db] Design and create the `analysts`, `sources` (one row per ingested video/blog link, with channel ID or blog domain captured for the matching task below), and `claims` tables per the "Claim schema" section in `CLAUDE.md` (including the trigger lifecycle fields listed in "Frontend and data model notes"); split a `verdicts`/resolution table out from `claims` if that's the cleaner shape. — Requested: 2026-09-02 18:14 MDT
- [ ] [db] Write CRUD functions: create analyst, list analysts, get analyst by id, create source + claim, list claims (with status/verdict filters), get claim by id, update claim on resolution. — Requested: 2026-09-02 18:14 MDT
- [ ] [matching] Implement the real analyst-matching algorithm: given a pasted URL, extract its channel ID (YouTube) or domain (blog), check against `sources` already on file, attach to that analyst if matched, otherwise let the frontend's existing "ask for a name" step create a new analyst. Replaces the mockup's `detectExpert()`/`detectSourceType()` placeholder (URL-substring match). — Requested: 2026-09-02 18:14 MDT
- [ ] [infra] Port `llm/client.py`'s structured-output client pattern from `youtube_fact_checker` (reusable infra; the extraction/evaluation prompts themselves are out of scope, see note below). — Requested: 2026-09-02 18:14 MDT
- [ ] [infra] Port `prices/ticker_resolver.py` and `prices/price_data.py` (yfinance fetching) from `youtube_fact_checker`, for the benchmark-comparison feature. — Requested: 2026-09-02 18:14 MDT
- [ ] [infra] Port `youtube/transcript.py` and `youtube/metadata.py` from `youtube_fact_checker`. — Requested: 2026-09-02 18:14 MDT
- [ ] [infra] Build a blog-post fetcher (no equivalent to port): given a URL, fetch the page and pull the article body out of it. Keep source-agnostic at the API boundary via a `sources.type` field; don't branch the rest of the pipeline on it. — Requested: 2026-09-02 18:14 MDT
- [ ] [api] `POST /links`: the single "Add a link" entry point. Runs the matching task above, fetches source content, creates the `sources` row and a `claims` row placeholder. Leave a clear seam, a stub such as `run_claim_finder(source_id)` or a job-queue entry, for the claim-finder LLM extraction to plug into; don't implement that extraction here. — Requested: 2026-09-02 18:14 MDT
- [ ] [api] `GET /analysts`, `GET /analysts/{id}` for Watchlist / Browse all / Expert profile screens. — Requested: 2026-09-02 18:14 MDT
- [ ] [api] `GET /claims`, `GET /claims/{id}` for the Claim detail screen, with the All/Open/Resolved filters the prototype's tabs need. — Requested: 2026-09-02 18:14 MDT
- [ ] [api] `POST /analysts/{id}/follow` (or similar) for the watchlist follow toggle already in the prototype. — Requested: 2026-09-02 18:14 MDT
- [ ] [api] Add a stub/scheduled-job entry point, no logic, for the claim analyzer's recurring re-check job, per the MVP scope's "plain scheduled jobs" note in `CLAUDE.md`. — Requested: 2026-09-02 18:14 MDT
- [ ] [frontend] Scaffold `frontend/` mirroring `../youtube_fact_checker/frontend`'s React/Vite/TS tooling. — Requested: 2026-09-02 18:14 MDT
- [ ] [frontend] Port the 5 screens from `design/mockup/prototype/index.html` (Watchlist, Browse all, Expert profile, Claim detail, Add-link flow) into real components, matching its design tokens/fonts exactly per "Frontend and data model notes" in `CLAUDE.md`. — Requested: 2026-09-02 18:14 MDT
- [ ] [frontend] Wire each screen to the real endpoints from the `[api]` tasks above, replacing the prototype's hardcoded `getAnalysts()`/`getClaims()`/`getDraftClaims()` fixtures. — Requested: 2026-09-02 18:14 MDT
- [ ] [frontend] Preserve the prototype's already-validated interactions (search/filter, follow toggle, claim filter tabs, draft-claim checklist in the review step, "Not them?" override in the add-link flow); don't redesign them. — Requested: 2026-09-02 18:14 MDT

**Not in scope for Codex**: anything inside the claim-finder/claim-analyzer/meta-analyst-analysis
prompts themselves, i.e. the actual LLM extraction and evaluation logic. Those get built
separately, per the Division of labor section in `CLAUDE.md`.
