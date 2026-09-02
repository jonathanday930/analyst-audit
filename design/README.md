# UI mockup — for reference, not reuse

This is the clickable prototype of the AnalystAudit frontend. Original,
built with Claude Design (a Claude Code skill), requires a Claude login to
view: https://claude.ai/code/artifact/5a74ed4b-3c44-4221-afc4-9bdcdfba3003

## The best way to hand this to another tool

**`mockup/prototype/index.html`** — a real, fully clickable prototype with
no login, no build step, no dependencies besides a Google Fonts CDN link.
Open it directly in any browser (double-click, or `open
design/mockup/prototype/index.html`). It's a from-scratch port of the
Claude Design mockup's exact behavior into plain HTML/CSS/vanilla JS —
same screens, copy, styling, and interactions:

- Navigate Watchlist / Browse all / Expert profile / Claim detail / Add flow
- Search and filter, toggle an expert's follow state
- Full "Add a link" auto-detect flow: paste a URL, it matches known experts
  or asks for a name if unrecognized, with the "Not them?" override
- Claim filter tabs (All / Open / Resolved), draft-claim checklist toggling
  in the review step

It's a single ~700-line file (state object + small render functions +
event delegation via `data-act` attributes) — plain enough for a coding
tool to read as reference *and* to edit directly if useful, unlike the
original's proprietary templating format. It uses the same hardcoded
fixture data as the original (no real backend), so it's still a mockup, not
the app.

## Other formats (screenshots / static per-screen HTML)

- `mockup/screenshots/` — a PNG per screen, for a quick look without
  opening anything.
- `mockup/static-html/` — one resolved, non-interactive HTML file per
  screen (a frozen snapshot, buttons don't do anything). Mostly superseded
  by `prototype/index.html` above, which covers the same ground and is
  actually clickable.

## Don't open Main.dc.html in a browser

`mockup/Main.dc.html` is Claude Design's own template source (the original
artifact's source of truth) — it only renders correctly inside Claude
Design's runtime. Opened directly in a plain browser, `{{handlebars}}`
holes show up as literal text and `<sc-if>`/`<sc-for>` conditionals/loops
don't run — it looks broken because it's missing the piece that resolves
it. Use `prototype/index.html` instead for anything that needs to actually
work in a browser; read `Main.dc.html` only if you want the original
source next to the port (same content, different implementation).

## Architecture and product decisions

This mockup is UI/UX only. For the actual system being built (pipeline
stages, claim schema, MVP scope, onboarding-flow rationale, benchmark-
comparison rationale), read `../CLAUDE.md` first — it's the authoritative
architecture doc and explains *why* the UI works the way it does (e.g. why
onboarding asks for a channel/feed URL, why evaluation includes a benchmark
comparison).
