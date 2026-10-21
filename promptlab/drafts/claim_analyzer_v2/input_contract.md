# What the claim analyzer gets fed (redesign draft v1)

The prompt in `prompt.md` assumes this user turn. It is a change from what
`resolve_claim` sends today, so the two have to land together.

## Why change the input at all

Today the pass receives every daily close in the window (roughly 250 lines for a one year swing
claim) and is expected to find the high, the low and the percentage change itself. That is
arithmetic, which is the one thing a model should not be doing when a price series is sitting
right there in Python. It is also where the wrong-baseline problem comes from: with only a raw
list, "since the call" and "over the target window" are easy to mix up.

So: code computes every number, the model judges. Three practical wins. Cheaper (a facts block
plus sampled closes is a fraction of the tokens). More accurate (no arithmetic, no baseline
ambiguity). Auditable (the numbers on the claim row are the same ones the model saw, because they
were computed once, in code, before the call).

## The block to send

```
CLAIM
Asset: Bitcoin
Resolved ticker: BTC-USD
Asset class: crypto
Claim: Bitcoin reaches $120,000
Stated implication: hold through the volatility
Condition/trigger: none (unconditional)
Horizon: swing
Analyst's stated invalidation: a weekly close below $70,000; the Fed restarting hikes
Source published: 2026-01-14
Today: 2026-09-08

WINDOW
Evaluation window: 2026-02-13 to 2027-01-14
Grace period runs to: 2027-02-25
Window state: open (128 days remaining)
Trigger deadline: n/a (unconditional claim)

PRICE RECORD for BTC-USD (closing prices, USD)
Baseline (first close on or after the claim): 2026-01-14  $94,210
Latest close: 2026-09-05  $101,880
Change since claim: +8.1%
High since claim: 2026-04-22  $118,340  (+25.6%)
Low since claim: 2026-02-28  $76,050  (-19.3%)
Monthly closes: 2026-01-31 $88,400 | 2026-02-27 $76,900 | ... | 2026-08-29 $99,120
```

Rules for building it:

- **Baseline** is always the first close on or after the source's published date. It is the only
  baseline; never re-baseline to the window start.
- **Asset class** is one of `broad index/ETF`, `single stock`, `crypto`, `commodity`, `other`, and
  it drives the magnitude thresholds in step 4 of the prompt. Derive it in code from the resolved
  ticker (the `_benchmark_ticker` crypto heuristic already does half of this).
- **Window state** is `open (N days remaining)`, `closing (under 30 days remaining)`,
  `in grace period (N days past the deadline, grace ends in M days)` or `closed (N days ago)`.
  The model does no date arithmetic.
- **Grace period** is `window_end` plus a flat allowance by horizon: 2 weeks for short-term,
  6 weeks for swing, 3 months for long-term, 6 months for structural. A claim stays pending
  through it, and an outcome that lands inside it is graded as if it were on time (see "Timing
  tolerance" in the prompt). Flat per horizon rather than proportional, because a proportional
  grace grows exactly where the window is already widest and least informative.
- **Sampled closes** are monthly for windows over 6 months, weekly under that. Path shape only;
  every number the prompt actually needs is already in the facts above them.
- **Missing data** is stated explicitly, e.g. `No price data available for this ticker`, never
  silently omitted. The prompt tells the model to fall back to web search for events and to
  return unverifiable rather than invent a figure.
- **Analyst's stated invalidation** comes from the claim finder's `rebuttal_invalidation`. It is
  passed so the model can spot an invalidation that actually fired, which is a legitimate early
  resolve to incorrect.
- `grounds`, `warrant`, `backing`, `qualifier` and `confidence` are deliberately **not** passed.
  Grading is on the outcome, and confidence in the input is confidence leaking into the verdict.
  The one exception is `right_for_stated_reasons`, which only needs the warrant in one line; pass
  the top warrant if that field proves useful, otherwise leave it out.

## What moves out of the model and into code

| Thing | Today | Proposed |
|---|---|---|
| High, low, % change since the call | model reads a 250 line list | computed in `price_facts.py`, passed in |
| Evaluation window dates | computed in code, recomputed inline three times | computed once, passed in, with a window state label |
| Benchmark comparison | benchmark series sent to the model | model returns `implied_direction`, code computes beat/lagged after the call |
| Next check date | not produced | model returns `recheck_in`, the scheduler turns it into a date |
| Lateness | not represented | `grace_end` in, `timing` out, verdict only drops past the grace |

The benchmark flip is the notable one. Whether a call beat the S&P is pure arithmetic once you
know which side of the trade being right meant, and that side is the only part a model is needed
for. It also removes a second full price series from the prompt.

## Web search budget

`WEB_SEARCH_TOOL` is capped at `max_uses: 3` today. Event-conditional claims can need a condition
check and an outcome check, so raise it to 5 for this pass. The prompt asks for at most two
targeted searches per open question, and for pending/unverifiable rather than a guess if search
comes back thin.

## Trying it in the prompt lab before the schema lands

The lab's claim analyzer tab runs the committed `ClaimResolution` schema, so a run of this prompt
would get quietly refitted into the old fields and look like the rewrite did nothing. Use raw
mode for the first pass (that is exactly what `complete_text` exists for), then promote both the
prompt and the schema together. Pin a claim set from a past run first, per the README, so the
comparison is not confounded by claim finder drift.
