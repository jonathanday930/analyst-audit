# Claim analyzer v3: what the model gets, and what code has to change

The prompt in `prompt.md` assumes the model is handed facts and never computes them. This file
specifies the user-message packet that has to hold up that assumption, and the changes in
`backend/src/app/prices/` and `preview_pipeline.py` needed to build it. Nothing here is
implemented yet.

## The user message

Six blocks, in this order.

### 1. As of

```
AS OF: 2026-09-08
```

Everything after this date is invisible to the analysis. This is what makes a re-check on a
schedule reproducible.

### 2. Source

Analyst name, source title, URL, source type, publication date. The publication date is the
default `window_start` and the price baseline, so it is load bearing rather than decoration.

### 3. The claim

Every field the claim finder produced, verbatim: `asset_description`, `suggested_ticker`,
`condition_trigger`, `claim`, `stated_implication`, `grounds`, `warrant`, `backing`, `qualifier`,
`confidence`, `rebuttal_invalidation`, `horizon`.

`rebuttal_invalidation` matters more than it looks. It is the analyst's own stated kill switch,
and section 6 of the prompt uses it as the one licence to call a claim incorrect before its
window closes.

`confidence` and `qualifier` are included so the model can see the claim as stated, and the
prompt explicitly forbids letting them shade the verdict.

### 4. Sibling claims from the same source

Just the `claim` text of the other claims extracted from the same source, as a list, labelled as
context only. This exists so the model can recognise a bear/base/bull scenario set and fill in
`scenario_label`, and so it does not read a bear case as the analyst's actual expectation.
InvestAnswers's Bitcoin video is the clean example: three price targets, 150k, 225k, and 400k,
extracted as three separate claims by design.

### 5. Market data

One block per instrument, all of it computed in code from yfinance. The point is that the model
can answer "did it ever reach $X between these dates" for any $X, without knowing $X in advance
and without doing arithmetic.

```
MARKET DATA (source: yfinance, adjusted closes)

SUBJECT: GDX (one of AEM, FNV, GDX resolved from "Gold mining stocks"; all three follow)
  Baseline close 2025-04-15: 44.12
  Latest close 2026-09-08:   71.80
  Change baseline to latest: +62.7%
  Highest close in span:     73.05 on 2026-08-21
  Lowest close in span:      41.90 on 2025-04-22
  Monthly detail (month | first close | last close | high close and date | low close and date):
    2025-04 | 44.12 | 45.30 | 45.88 on 2025-04-29 | 41.90 on 2025-04-22
    2025-05 | ...

COMPARISON: none
BENCHMARK: SPY
  Baseline close 2025-04-15: 537.61
  ... same shape ...
```

Rules for building it:

- The span always runs from the publication date to the as-of date, never from a window the
  model chose. The model narrows to its own window by reading the monthly rows.
- Monthly granularity is enough for swing and longer claims and keeps the block small. For a
  `short-term` horizon claim, use weekly rows instead, since a six week window has only one or
  two monthly rows in it.
- Emit the block even when the claim is macro. The prompt tells the model to treat price data as
  context and not as evidence for a recession call, but having it there stops the model from
  guessing at market context it half remembers.
- When a series cannot be fetched, say so explicitly in the block rather than omitting it
  silently, so the model puts it in `data_gaps` instead of inventing a number.

### 6. Search guidance

One line naming what specifically needs verifying, when `evidence_needed` is likely to be
`web_only` or `price_and_web`. Built in code from a cheap heuristic: no resolved ticker, or the
claim mentions recession, GDP, CPI, the Fed, an election, an approval, or a ceasefire.

## Code changes this needs

Re-audited against the current `ticker_resolver.py` and `preview_pipeline._check_claim` (all 37
claims in the frozen short set).

### Already done

`resolve_tickers()` now tries `suggested_ticker` before the alias table and returns every valid
ticker, and `_check_claim` fetches a series per ticker and passes the list through to
`resolve_claim`. That fixed all three of the mis-resolutions found earlier: gold mining stocks
now give AEM, FNV, GDX rather than `GC=F`; the Magnificent 7 give their seven tickers rather than
SPY; QQQ versus SCHD gives both.

Two side effects worth knowing. The alias table now fires on **zero** of the 37 claims, because
the claim finder supplies `suggested_ticker` whenever there is a tradeable subject at all, so it
is effectively stance-only code now. And the four claims with no tradeable subject (three
recession calls plus one on US housing) resolve to an empty list, which is the right answer:
under this prompt a recession call is settled by GDP prints and the NBER, not by SPY.

### Still open: the benchmark is the claim's own subject on 11 of 37 claims

`_benchmark_ticker` was not part of that change, and it is now the largest defect left in the
packet. It returns `BTC-USD` for anything crypto flavoured and `SPY` for everything else, with no
awareness of what the claim already resolved to:

| Claims | Subject | Benchmark | Result |
|---|---|---|---|
| 4 Benjamin Cowen, 1 New Money | `^GSPC`, `SPY` | `SPY` | SPY measured against SPY |
| 1 Bravos Research | `SPY`, `^GSPC` | `SPY` | same |
| 1 Coin Bureau, 4 InvestAnswers | `BTC-USD` | `BTC-USD` | Bitcoin measured against Bitcoin |

Every Bitcoin price target in the set, and every S&P call, currently gets a benchmark comparison
that is arithmetically guaranteed to be a tie. The prompt now tells the model to skip the
benchmark when the subject is the broad market, but it should not be handed a degenerate
benchmark in the first place. A rule that covers the whole set:

- Subject is a broad US index proxy (`SPY`, `^GSPC`, `VOO`, `IVV`, `QQQ`, `^NDX`, `DIA`, `^DJI`):
  no benchmark. Nothing meaningful to compare against.
- Subject is Bitcoin: benchmark `SPY`. "Would you have done better in an index fund" is exactly
  the question CLAUDE.md's benchmark section asks, and it is the one comparison that says
  something here.
- Subject is any other crypto: benchmark `BTC-USD`. This is the case the existing crypto branch
  was actually built for.
- Subject is a yield or index level (`^TNX`, `^VIX`, `DX-Y.NYB`): no benchmark.
- Everything else: benchmark `SPY`.
- Belt and braces: never return a benchmark that appears in the resolved ticker list.

### Still open: alternative listings of the same exposure are fetched twice

`suggested_ticker` often lists two ways to hold one thing: `['^GSPC', 'SPY']` on five claims,
`['GC=F', 'GLD']`, `['BRK-B', 'BRK-A']`. Each one currently costs a yfinance fetch and a full
block of monthly rows in the prompt, for no extra information, and it gives the model two nearly
identical series to choose from when it goes to compare against a target level.

Collapse known equivalence groups to their first member before fetching: `{SPY, ^GSPC, VOO,
IVV}`, `{QQQ, ^NDX}`, `{DIA, ^DJI}`, `{GC=F, GLD}`, `{SI=F, SLV}`, `{BRK-A, BRK-B}`. Genuine
baskets, the Magnificent 7's seven tickers or Peter Schiff's AEM, FNV, GDX, are not equivalence
groups and all of them still get fetched.

### Still open: yields and index levels need labelling in the market data block

`^TNX` is a yield in percent, so a move from 4.0 to 4.4 is 40 basis points, not a 10% gain.
`^VIX` and `DX-Y.NYB` are the same shape of problem. The block builder should mark these series
as levels and suppress the "change baseline to latest" percentage for them, so the model is never
shown a number that invites the wrong reading. The prompt tells the model to expect that label.

### Still open: multi-instrument claims need the roles spelled out in the block

Now that several series arrive together, the block has to say which is which, or the model has to
guess. Label each series `SUBJECT`, `COMPARISON`, or `BENCHMARK` when the shape is knowable in
code, and where it is not, list them all as subjects and let the model assign roles into
`subject_tickers` and `comparison_tickers`. The one reliable signal available in code is a
resolved list of exactly two where the `asset_description` contains "relative to", "versus", "vs",
or "compared to".

### Still open: search budget

`WEB_SEARCH_TOOL` is capped at `max_uses: 3` in `client.py`. Fine for a price claim that needs no
search, tight for a recession call that has to establish two quarters of GDP plus the NBER
position. Worth raising to 5 for claims the macro heuristic flags, and leaving at 3 otherwise.

### Worth doing once the packet is right: deterministic cross-check

`test.target_value`, `target_direction`, `window_start`, and `window_end` are machine readable on
purpose. Once a resolution comes back, code can independently answer "was that level touched
inside that window" from the same yfinance data and flag disagreement with the model's `checks`
outcome. That is a free accuracy harness over the frozen short set and it needs no database.

## Open questions

- **Structural claims never resolve.** "Berkshire is virtually indestructible" and "Microsoft is
  a lifetime hold" are five of the ten Joseph Carlson and New Money claims in the short set.
  Under this design they return `too_early` forever with progress attached. That is honest, but
  it means a chunk of every buy-and-hold analyst's record stays permanently unscored. The
  alternative is a rolling annual scorecard for structural claims, judged against the benchmark
  over each year, which is a stage 3 decision more than an analyzer one.
- **Analyst-behaviour claims.** "He will eventually buy QQQ" is `unfalsifiable` here. Arguably
  the claim finder should not be emitting it at all, which would be a claim-finder scope change
  rather than an analyzer change.
