# UI mockup — for reference, not reuse

`mockup/Main.dc.html` is the clickable prototype of the AnalystAudit frontend,
built with Claude Design (a Claude Code skill). Live version:
https://claude.ai/code/artifact/5a74ed4b-3c44-4221-afc4-9bdcdfba3003

**What it's good for:** it is the source of truth for every screen, field,
label, copy string, state transition, and interaction in the product —
more precise than any written spec, because it's the actual thing the user
clicked through and approved. Read it to answer "what does this screen show",
"what's the exact wording here", "what happens when the user does X".

**What it's NOT good for:** the file is not meant to be ported or adapted as
implementation code. It's written in Claude Design's own templating format
(`<x-dc>`, `{{handlebars}}` holes, `<sc-if>`/`<sc-for>`), and its data is a
`class Component extends DCLogic` doing everything client-side with hardcoded
fixture data (fake gurus/claims — no real backend, no persistence). Treat the
markup structure, CSS values (colors, spacing, type), and the `renderVals()`
logic as the spec to *reimplement* in whatever stack the real app uses — not
as code to copy in.

## How to read it

- The `<helmet>` block has the full design system: color tokens (dark
  "trading terminal" theme), fonts (Space Grotesk + JetBrains Mono via
  Google Fonts), and base styles.
- The markup is one big `<sc-if>` chain, one block per screen: **Watchlist**,
  **Browse all**, **Expert profile**, **Claim detail**, **Add flow**. Each
  screen's exact fields and layout are in its block.
- The `<script data-dc-script>` block at the bottom is the actual behavior:
  `getGurus()`/`getClaims()`/`getDraftClaims()` are the fixture data shape
  (a decent starting point for the real data model's fields), and
  `renderVals()` computes everything the templates bind to — this is where
  navigation, filtering, search, follow-toggle, and the multi-phase "Add a
  link" auto-detect flow (`detectSourceType`/`detectExpert`/`runDetection`)
  are all implemented.
- `canvas.json` is just Claude Design's layout manifest (single artboard) —
  no product information in it.

## Architecture and product decisions

This mockup is UI/UX only. For the actual system being built (pipeline
stages, claim schema, MVP scope, onboarding-flow rationale, benchmark-
comparison rationale), read `../CLAUDE.md` first — it's the authoritative
architecture doc and explains *why* the UI works the way it does (e.g. why
onboarding asks for a channel/feed URL, why evaluation includes a benchmark
comparison).
