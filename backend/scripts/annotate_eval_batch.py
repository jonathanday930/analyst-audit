#!/usr/bin/env python3
"""Layer a hand-written extraction review on top of a rendered preview_batch.py report.

preview_batch.py answers "what did the prompts produce"; this answers "is what they produced
any good". It injects, into an existing batch HTML file:

  * a per-claim REVIEW note appended to every claim card, tagged sound / minor / issue, and
  * a per-source review summary section, and
  * a leading "Extraction review" tab holding the cross-source findings.

The notes below are a manual review of one specific batch (the five Bravos Research / Camel
Finance videos in output/eval-batch.html), checked against transcripts re-fetched with
app.sources.fetcher. They are keyed by (panel index, claim index) so re-running this script on
the same file is idempotent, but they do NOT survive re-running preview_batch.py itself, which
regenerates the report from scratch and produces different claims. Re-review after a re-run.

Usage:
    python scripts/annotate_eval_batch.py scripts/output/eval-batch.html
    python scripts/annotate_eval_batch.py IN.html --out OUT.html
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MARKER = "<!-- extraction-review-injected -->"

# --- review CSS (extends the batch report's own tokens; no new palette) ----------------------

_REVIEW_CSS = """
  .review { margin-top: 12px; padding: 11px 13px; border-radius: 8px;
            border-left: 3px solid var(--accent); background: rgba(227,166,58,0.05);
            font-size: 13px; line-height: 1.55; color: var(--text-muted); }
  .review--sound { border-left-color: var(--good); background: rgba(79,191,122,0.05); }
  .review--minor { border-left-color: var(--pending); background: rgba(139,150,163,0.05); }
  .review--issue { border-left-color: var(--bad); background: rgba(224,97,107,0.06); }
  .review-tag { display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
                text-transform: uppercase; margin-right: 8px; vertical-align: 1px; }
  .review--sound .review-tag { color: var(--good); }
  .review--minor .review-tag { color: var(--pending); }
  .review--issue .review-tag { color: var(--bad); }
  .review strong { color: var(--text); font-weight: 600; }
  .review code { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px;
                 color: var(--accent); }
  .findings { counter-reset: finding; }
  .finding { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
             padding: 15px 18px; margin-bottom: 12px; }
  .finding h4 { margin: 0 0 8px; font-size: 14.5px; color: var(--text); font-weight: 600; }
  .finding p { margin: 0 0 8px; font-size: 13.5px; line-height: 1.6; color: var(--text-muted); }
  .finding p:last-child { margin-bottom: 0; }
  .finding code { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px;
                  color: var(--accent); }
  .finding strong { color: var(--text); font-weight: 600; }
  .sev { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px;
         font-weight: 700; letter-spacing: 0.07em; margin-left: 8px; vertical-align: 2px; }
  .sev--high { color: var(--bad); background: var(--bad-soft); }
  .sev--med { color: var(--accent); background: var(--accent-soft); }
  .sev--low { color: var(--pending); background: var(--pending-soft); }
  table.tally { border-collapse: collapse; width: 100%; font-size: 13px; margin-bottom: 24px; }
  table.tally th, table.tally td { text-align: left; padding: 7px 10px;
                                   border-bottom: 1px solid var(--border); }
  table.tally th { color: var(--text-faint); font-size: 11px; text-transform: uppercase;
                   letter-spacing: 0.05em; font-weight: 600; }
  table.tally td.num { font-family: 'JetBrains Mono', ui-monospace, monospace;
                       color: var(--text); white-space: nowrap; }
  .lede { font-size: 14px; line-height: 1.65; color: var(--text-muted); margin: 0 0 24px;
          max-width: 70ch; }
  .lede strong { color: var(--text); }
"""

# --- per-claim notes, keyed (panel index, 1-based claim index) -------------------------------
# (severity, html)
N = dict[tuple[int, int], tuple[str, str]]

CLAIM_NOTES: N = {
    # ---------- Panel 0: "We Just Sold Everything..." (2025-07-09) ----------
    (0, 1): ("sound", "Faithful to the source and well scoped. All three quotes are verbatim, and "
             "the two-month window matches &ldquo;the month or two that followed&rdquo;. Only nit: "
             "<code>horizon</code> is <code>short-term</code> (schema: &ldquo;days to a few "
             "weeks&rdquo;) on a 62-day window."),
    (0, 2): ("issue", "<strong>The return was measured off the wrong baseline.</strong> The claim "
             "is that the golden cross leads the market higher <em>over</em> the following 6&ndash;12 "
             "months, i.e. higher than it was on 2025-07-09. The window was set to "
             "<code>2026-01-09 &rarr; 2026-07-09</code>, and because "
             "<code>preview_pipeline.py</code> uses <code>target_window_start</code> as the price "
             "baseline, the analyzer graded the Jan&rarr;Jul 2026 return (+8.9%) and threw away the "
             "first six months of the very move it was grading. From the actual call date SPY went "
             "~617&rarr;752 (+22%), so the <em>good</em> verdict is right by accident, not by "
             "construction."),
    (0, 3): ("sound", "Good conditional modelling: the trigger (a stock-market pullback) is "
             "correctly separated from the outcome (Bitcoin holding up), which is what let the "
             "analyzer say &ldquo;the trigger fired but the outcome didn&rsquo;t&rdquo;. "
             "<code>horizon: short-term</code> is asserted even though "
             "<code>timeframe_as_stated</code> is null."),
    (0, 4): ("minor", "Extraction is right: one sentence naming three sectors correctly becomes "
             "three claims. But see the grading note on claims 5 and 6: all three share a "
             "trigger and should share a measurement window."),
    (0, 5): ("issue", "<strong>Three claims from one sentence, graded off three different "
             "baselines.</strong> Claims 4 and 6 measure from the trigger date (2025-08-01); this "
             "one measures from the publish date (2025-07-09). Same sentence, same trigger, same "
             "condition. The baseline must not vary per claim. All three are also graded over "
             "~13 months against an outcome the analyst framed as &ldquo;the next phase of the "
             "rally&rdquo; following a <em>short-term</em> pullback, which is a far more generous "
             "test than what was said."),
    (0, 6): ("minor", "Same baseline/window inconsistency as claim 5. The extraction itself is "
             "clean and the quotes are verbatim."),

    # ---------- Panel 1: "Ticking Higher - Bitcoin is Next!" (2025-11-08) ----------
    (1, 1): ("issue", "<strong>Five separable predictions welded into one claim.</strong> Blowoff "
             "top, bear market, global recession, asset-price deflation, and a &ldquo;lost "
             "decade&rdquo; are each independently checkable and each landed differently; grading "
             "them as one <em>bad</em> destroys that information. The window "
             "(&rarr;&nbsp;2026-03-31) is the analyst&rsquo;s deadline for the <em>top</em>, not for "
             "the recession or the lost decade. A lost decade cannot be falsified in five "
             "months. The benchmark line is also degenerate: a <code>^GSPC</code> claim benchmarked "
             "against SPY reports both legs at &minus;4.0% and then labels it &ldquo;trailed "
             "benchmark&rdquo;."),
    (1, 2): ("sound", "Correctly deferred rather than guessed: the window opens 2026-10-01. "
             "This is the eligibility logic working as intended."),
    (1, 3): ("sound", "Correctly deferred, same as claim 2."),
    (1, 4): ("sound", "Correctly deferred. Good catch that &ldquo;the end of next year&rdquo; means "
             "late 2026 from a 2025 source, not late 2025."),
    (1, 5): ("sound", "Together with claim 6, the best evidence in this batch that the "
             "&ldquo;don&rsquo;t collapse scenarios&rdquo; rule is doing real work: the "
             "bull case and the bear case for the same Bitcoin cycle are both on the record. "
             "One quote stitches two non-adjacent fragments with an ellipsis; both halves are "
             "genuinely in the transcript, but the joined form reads as one continuous sentence."),
    (1, 6): ("issue", "<strong>Nothing links this to claim 5, and they are mutually "
             "exclusive.</strong> The analyst explicitly offered these as either/or. Claim 5 is "
             "graded <em>bad</em> while this one stays <em>still pending</em>, so a track-record "
             "rollup will read one miss plus one open call out of what was a single hedged fork. "
             "The schema needs a claim-group / mutual-exclusion link before stage-3 scoring can be "
             "trusted."),
    (1, 7): ("sound", "Clean, specific, and genuinely falsifiable: negative CPI prints around "
             "mid-2026. The resolution cites the actual series."),
    (1, 8): ("issue", "<strong>Graded on evidence the rationale itself places outside the "
             "window.</strong> The window closed 2026-01-31 and the rationale awards <em>good</em> "
             "on confirmation &ldquo;materializing within roughly two to four weeks of the stated "
             "Jan 31 window close&rdquo;. Compare claims 6, 9 and 14, held pending because their "
             "windows are still open. The analyzer&rsquo;s willingness to reach past a window "
             "boundary is not consistent, and it is not recorded anywhere in the output."),
    (1, 9): ("sound", "Correctly left pending with nearly four months of the window remaining, and "
             "the rationale says plainly that current evidence leans against the claim. This is the "
             "behaviour claim 6 in panel 3 should have had."),
    (1, 10): ("sound", "<strong>The best-formed claim in the batch.</strong> Named event, exact "
              "date, exact magnitude, unambiguous resolution. Worth keeping as a regression "
              "fixture for the claim finder."),
    (1, 11): ("minor", "&ldquo;3 months plus past the rate cuts&rdquo; is open-ended on the far "
              "side; the extraction closed it at 2026-04-30, so the window end is invented rather "
              "than derived. The <em>good</em> verdict then rests on a 7.7% March drawdown that "
              "fully reversed inside the same window."),
    (1, 12): ("sound", "Nicely picked up: a throwaway &ldquo;should resolve higher in just "
              "days&rdquo; is exactly the kind of short-fuse, checkable call that a track-record "
              "system should be catching."),
    (1, 13): ("issue", "<strong>Composite outcome across three asset classes.</strong> The claim "
              "requires stocks <em>and</em> Bitcoin <em>and</em> precious metals to have topped. "
              "Bitcoin&rsquo;s leg was right, equities&rsquo; was wrong, metals were inconclusive "
              ", and the whole thing scores <em>bad</em>, so the analyst gets no credit for "
              "the leg they called correctly. Should be three claims. One supporting quote is also "
              "a paraphrase, not verbatim (see the quote-fidelity finding)."),
    (1, 14): ("sound", "Correctly pending: the trigger has not fired and its deadline has not "
              "passed. The rationale cites the actual HY OAS level rather than hand-waving."),

    # ---------- Panel 2: "Stocks are Getting Rug Pulled." (2025-03-28) ----------
    (2, 1): ("sound", "Tight, well-sized window for &ldquo;by the end of this year&rdquo;, and "
             "because the test is an absolute level (above the prior all-time high) the "
             "window-start-as-baseline problem doesn&rsquo;t bite here."),
    (2, 2): ("minor", "<code>target_window_start</code> is 2025-01-01, which precedes the source&rsquo;s "
             "2025-03-28 publish date, so the claim is partly graded over a period before it "
             "was made. Harmless for a calendar-year recession call, but nothing in the schema "
             "forbids it, and it would silently corrupt any price-based claim."),
    (2, 3): ("issue", "<strong>A double-negative hedge scored as a hit.</strong> The source is "
             "&ldquo;seeing another big dip down at a generally choppy market over the next month "
             "wouldn&rsquo;t really not surprise us&rdquo;, about the weakest form a "
             "prediction can take. It is graded <em>good call</em> with the same weight as claim "
             "10 in panel 1 (a dated, sized Fed call). Nothing in the schema records the "
             "difference."),
    (2, 4): ("issue", "<strong>A risk being monitored, recorded as a forecast.</strong> The source "
             "says &ldquo;we think one of the <em>risks</em> in today&rsquo;s market is&hellip;&rdquo; "
             ". The analyst is naming a thing they are watching, not predicting it. Extracted "
             "as an unconditional prediction and scored <em>bad</em>, i.e. the analyst is penalised "
             "for correctly flagging a risk that didn&rsquo;t materialise."),
    (2, 5): ("issue", "<strong>Directly contradicts claim 4&rsquo;s resolution, in the same "
             "batch.</strong> Claim 4 was graded <em>bad</em> on the finding that tech did <em>not</em> "
             "underperform the S&amp;P. This claim&rsquo;s rationale states the opposite: "
             "&ldquo;the conditional &lsquo;significant tech unwind vs S&amp;P 500&rsquo; "
             "materialized in March 2026&rdquo;, and grades <em>good</em>. Same event, two "
             "opposite factual findings, analyst penalised once and credited once. Claims are "
             "resolved in isolation with no cross-claim consistency pass over a single source."),

    # ---------- Panel 3: "It's Happening Again..." (2025-02-04) ----------
    (3, 1): ("issue", "<strong>Someone else&rsquo;s forecast, credited to the analyst.</strong> The "
             "source is &ldquo;the tax Foundation estimates that the average tariff rate&hellip; "
             "could rise to nearly 17.7%&rdquo;. The 17.7% is the Tax Foundation&rsquo;s number; the "
             "analyst&rsquo;s own contribution is only the framing that this would be the highest "
             "since the Great Depression. Graded <em>good call</em>, which hands the analyst a hit "
             "for a third party&rsquo;s work. The schema has no field distinguishing "
             "&ldquo;asserted&rdquo; from &ldquo;cited&rdquo;."),
    (3, 2): ("minor", "Same attribution problem (&ldquo;estimates currently suggest&hellip;&rdquo;). "
             "Correctly left pending on a decade-long window, which makes claim 6 below, "
             "resolved 2.4 years early, harder to defend."),
    (3, 3): ("sound", "This one <em>is</em> the analyst&rsquo;s own contrarian call (one-off price "
             "level shift, not structural inflation) and it is well captured, with the quantified "
             "1.5% and the reasoning both quoted. Good resolution too: it separates the "
             "tariff-specific effect from headline CPI noise instead of grading the headline."),
    (3, 4): ("minor", "Sound extraction, but no window at all on the batch&rsquo;s single most "
             "consequential claim (&ldquo;the bull run continues&rdquo;), so the ~19-month grading "
             "period is the analyzer&rsquo;s choice rather than the analyst&rsquo;s."),
    (3, 5): ("sound", "Model conditional claim: a real trigger, a trigger deadline (2025-06-30) that "
             "sits <em>before</em> the outcome window (2025-07-01&rarr;12-31), and a resolution that "
             "confirms the trigger fired before judging the outcome. This is the shape the other "
             "conditionals should follow."),
    (3, 6): ("issue", "<strong>Resolved 2.4 years before its own window closes.</strong> The window "
             "runs to 2029-01-20 and the claim was graded <em>bad</em> as of 2026-09. Claim 2 above, "
             "on a comparable multi-year window, was correctly left <em>still pending</em>, so "
             "the analyzer applies two different rules to the same situation inside one source. The "
             "source language is also maximally hedged (&ldquo;one could speculate&hellip;&rdquo;)."),
    (3, 7): ("minor", "Good extraction of a negative prediction (nothing will happen), which is "
             "easy to miss. <code>horizon: short-term</code> on a 181-day window is well outside the "
             "schema&rsquo;s own definition."),

    # ---------- Panel 4: "Please Don't Be Dumb Money..." (2025-08-21) ----------
    (4, 1): ("issue", "<strong>Unfalsifiable by construction, graded as a hit.</strong> &ldquo;The "
             "stock market <em>could</em> still be vulnerable to some additional downside&rdquo; "
             "cannot fail: any dip confirms it, and no dip is explained by the same "
             "sentence&rsquo;s bullish half. The rationale even calls it &ldquo;the analyst&rsquo;s "
             "hedged near-term call&rdquo; and awards <em>good</em> on a 1.3% wobble. The benchmark "
             "line is degenerate too: <code>^GSPC</code> vs SPY, both +4.7%, reported as "
             "&ldquo;trailed benchmark&rdquo;."),
    (4, 2): ("minor", "No window, graded over ~12.5 months of the analyzer&rsquo;s choosing. "
             "&ldquo;Plenty of room to run higher&rdquo; has no magnitude, so almost any positive "
             "return scores."),
    (4, 3): ("sound", "Clean: explicit, dated, and genuinely the analyst&rsquo;s own position. "
             "Resolution cites GDP prints and the NBER rather than the index level."),
    (4, 4): ("issue", "Source is &ldquo;<em>may</em> be about to turn around&rdquo; on a point the "
             "analyst explicitly declines to argue in this video. Extracted with "
             "<code>horizon: structural</code> (a multi-year secular thesis) despite no stated "
             "timeframe, then graded on 12.5 months. The horizon label and the grading "
             "period disagree with each other and neither comes from the source."),
    (4, 5): ("issue", "<strong>Asset and ticker don&rsquo;t match the outcome.</strong> The asset is "
             "investor sentiment / a topping signal; the ticker is <code>^GSPC</code>, whose price "
             "series cannot test a claim about AAII bearishness. The source is also an on-screen "
             "illustration plus a statement about the analyst&rsquo;s own future strategy "
             "(&ldquo;at that point, we&rsquo;ll be shifting our strategy&rdquo;), not a forecast. "
             "Graded <em>bad</em>."),
    (4, 6): ("minor", "Extraction is correct per the schema, but note what it does to scoring: one "
             "throwaway sentence listing five current holdings generates claims 6&ndash;10, i.e. "
             "<strong>half this video&rsquo;s scorecard, all scored <em>good</em></strong>, from a "
             "single line. These five also duplicate stances 4&ndash;8, extracted from the very same "
             "sentence."),
    (4, 7): ("issue", "<strong>The pass/fail standard silently changes between claims.</strong> D "
             "returned +1.6% against SPY&rsquo;s +5.6% and scores <em>good</em> (absolute standard); "
             "panel 0 claim 5 saw XLI return +16.8% against SPY&rsquo;s +24.0% and scores <em>bad</em> "
             "(relative standard). Both are defensible readings of the respective wordings, but "
             "nothing in the output records which standard was applied, so the two verdicts are not "
             "comparable and stage-3 scoring will mix them."),
    (4, 8): ("sound", "Fine as extracted; carries the same one-sentence-five-claims weighting "
             "caveat as claim 6."),
    (4, 9): ("sound", "Fine as extracted; same weighting caveat."),
    (4, 10): ("sound", "Fine as extracted; same weighting caveat. The +22.9% resolution is the only "
              "one of the five where &ldquo;perform well&rdquo; is unambiguous."),
}

# --- per-source review summaries -------------------------------------------------------------

PANEL_SUMMARIES: dict[int, str] = {
    0: "<p><strong>Extraction: strong. Grading: inconsistent.</strong> All 20 quotes are verbatim, "
       "the pullback thesis and the golden-cross thesis are correctly kept as two separate claims "
       "even though they point opposite ways, and the three sector calls are correctly split out of "
       "one sentence. The problems are all downstream: claim 2 is graded off a baseline six months "
       "after the call was made, and claims 4&ndash;6 (one sentence, one trigger) are "
       "graded off three different baselines over a 13-month window for what the analyst framed as "
       "the rally following a short-term dip.</p>",
    1: "<p><strong>The hardest source in the batch, and the most revealing.</strong> 14 claims from "
       "a 27k-character rambling transcript, and the finder held up well: it caught the dated Fed "
       "call, the &lsquo;resolves higher in days&rsquo; throwaway, and, crucially, both "
       "sides of the analyst&rsquo;s explicit bull/bear fork on Bitcoin (claims 5 and 6), which is "
       "the behaviour <code>CLAUDE.md</code> specifically asks for. It also correctly deferred three "
       "claims whose windows have not opened. Against that: this is the only source with "
       "non-verbatim quotes (3 of them), and it produced the batch&rsquo;s two worst composite "
       "claims: claim 1 (five predictions, one verdict) and claim 13 (three asset classes, "
       "one verdict).</p>",
    2: "<p><strong>Only five claims, but they contain the batch&rsquo;s clearest logical failure.</strong> "
       "Claims 4 and 5 are resolved against directly contradictory findings about the same event "
       "(did tech underperform in 2026 or not), and the analyst is penalised for one and credited "
       "for the other. Two of the five (claims 3 and 4) also rest on language that isn&rsquo;t a "
       "prediction at all: a &ldquo;wouldn&rsquo;t surprise us&rdquo; and a "
       "&ldquo;one of the risks&rdquo;, yet carry the same weight as everything else. The "
       "stance extractor did well here by contrast: five specific positions and a correctly "
       "bearish read on homebuilders.</p>",
    3: "<p><strong>Good coverage of a discursive macro essay, undermined by attribution.</strong> The "
       "finder correctly picked up the analyst&rsquo;s genuinely contrarian call (tariffs cause a "
       "one-off price shift, not structural inflation) and a well-formed conditional with a real "
       "trigger deadline. But its two highest-profile claims (1 and 2) are third-party estimates the "
       "analyst was quoting, not asserting, and claim 1 is scored as a hit for the analyst on that "
       "basis. Claim 6 is also resolved 2.4 years before its window closes, while claim 2 on a "
       "similar window is correctly held open. The three &lsquo;long&rsquo; stances all come from one "
       "retrospective sentence about having benefited over the <em>past</em> year, recorded as "
       "current positions.</p>",
    4: "<p><strong>The weakest source for claim quality, and it isn&rsquo;t the finder&rsquo;s "
       "fault.</strong> The video is mostly hedged commentary, and the finder faithfully extracted "
       "it. Four of ten claims rest on &ldquo;could&rdquo;/&ldquo;may&rdquo;/&ldquo;it could "
       "be that&rdquo;, and five more come from a single sentence listing current holdings. The "
       "result is a 9-of-10 <em>good call</em> scorecard that badly overstates what this analyst "
       "actually put on the record. This is the clearest argument in the batch for a "
       "<code>conviction</code> field: the finder is doing its job, and the scoring layer has no way "
       "to tell a hedge from a call.</p>",
}

# --- cross-source findings tab ----------------------------------------------------------------

_REVIEW_PANEL = """<div class="panel active">
<div class="header">
  <h2>Extraction review</h2>
  <div class="meta-row">
    <span class="badge badge--outline">MANUAL REVIEW</span>
    <span>5 sources &middot; 42 claims &middot; 38 stances &middot; 109 supporting quotes</span>
    <span>&middot;</span>
    <span>Transcripts re-fetched via <span class="mono">app.sources.fetcher</span></span>
  </div>
</div>

<p class="lede">Every supporting quote was checked verbatim against a freshly re-fetched
transcript, and every claim against what the analyst actually said around it. <strong>The claim
finder is in good shape</strong>: it is faithful to the source, it splits multi-asset
sentences correctly, and it keeps contradictory bull/bear scenarios apart exactly as
<span class="mono">CLAUDE.md</span> asks. <strong>The problems cluster in what the schema
doesn&rsquo;t capture and in how the analyzer grades</strong>: hedges are indistinguishable from
convictions, composite claims get one verdict, windows double as price baselines, and two claims
from the same video can be resolved against contradictory findings.</p>

<section>
  <h3>By the numbers</h3>
  <table class="tally">
    <tr><th>Measure</th><th>Count</th><th>Note</th></tr>
    <tr><td>Claims extracted</td><td class="num">42</td><td>6 / 14 / 5 / 7 / 10 across the five sources</td></tr>
    <tr><td>Verdicts</td><td class="num">22 good &middot; 13 bad</td><td>63% hit rate on the 35 graded claims</td></tr>
    <tr><td>Correctly deferred</td><td class="num">4 pending &middot; 3 not due</td><td>Eligibility logic working as designed</td></tr>
    <tr><td>Quotes verbatim</td><td class="num">105 / 109</td><td>3 paraphrased-as-verbatim, 1 legitimate ellipsis stitch</td></tr>
    <tr><td>Claims graded with no window at all</td><td class="num">11 / 35</td><td>31%, grading period chosen by the analyzer</td></tr>
    <tr><td>Claims resting on hedged language</td><td class="num">14 / 42</td><td>10 of them got a hard good/bad verdict</td></tr>
    <tr><td>Horizon label outside its own schema band</td><td class="num">4</td><td>All <span class="mono">short-term</span> on 2&ndash;6 month windows</td></tr>
    <tr><td>Degenerate benchmarks</td><td class="num">2</td><td><span class="mono">^GSPC</span> claims benchmarked against SPY</td></tr>
  </table>
</section>

<section>
  <h3>What the claim finder gets right</h3>
  <div class="findings">
    <div class="finding">
      <h4>The no-collapse rule earns its keep</h4>
      <p>Panel 1 claims 5 and 6 are the bull and bear cases for the same Bitcoin weekly cycle, both
      on the record, exactly as intended. Panel 0 does the same with a short-term pullback call
      sitting alongside a 6&ndash;12 month bullish call. A trade-action framing would have collapsed
      both and lost the information.</p>
    </div>
    <div class="finding">
      <h4>Quote fidelity is high enough to review against</h4>
      <p>105 of 109 quotes are verbatim. That is what made this review possible at all: the
      <span class="mono">supporting_quotes</span> field is doing the job the prompt asks of it.</p>
    </div>
    <div class="finding">
      <h4>Deferral logic is sound</h4>
      <p>Seven claims were correctly left ungraded: three whose windows have not opened, four
      still genuinely open. Panel 1 claim 9&rsquo;s rationale even states that current evidence leans
      against the claim while still refusing to grade it early. That is the right instinct.</p>
    </div>
    <div class="finding">
      <h4>Conditionals are modelled properly</h4>
      <p>Panel 3 claim 5 is the model case: a real trigger, a trigger deadline that sits before the
      outcome window, and a resolution that confirms the trigger fired before judging the outcome.
      Panel 0 claim 3 correctly reports &ldquo;trigger fired, outcome failed&rdquo;.</p>
    </div>
  </div>
</section>

<section>
  <h3>Findings</h3>
  <div class="findings">

    <div class="finding">
      <h4>1. A hedge and a conviction are scored identically<span class="sev sev--high">high</span></h4>
      <p><strong>14 of 42 claims</strong> rest on &ldquo;could&rdquo;, &ldquo;may&rdquo;, &ldquo;it
      could be that&rdquo;, &ldquo;one could speculate&rdquo;, or &ldquo;wouldn&rsquo;t really not
      surprise us&rdquo;, and 10 of those received a hard good/bad verdict carrying the same weight
      as panel 1 claim 10 (&ldquo;the Fed cuts 25bp on December 10&rdquo;, dated and sized).</p>
      <p>Worst cases: panel 4 claim 1 (&ldquo;the market <em>could</em> still be vulnerable to some
      additional downside&rdquo;, unfalsifiable, scored <em>good</em> on a 1.3% wobble) and
      panel 2 claim 3 (a double-negative, scored <em>good</em>). Panel 4&rsquo;s 9-of-10 scorecard is
      the visible consequence: it reads as a strong track record for what was mostly hedged
      commentary.</p>
      <p><strong>Fix:</strong> add <span class="mono">conviction</span> to
      <span class="mono">ClaimExtraction</span>, something like <span class="mono">base-case /
      hedged / risk-flagged / cited</span>, captured from the analyst&rsquo;s own wording, and
      let stage 3 weight by it. This does not require changing what gets extracted, only recording
      how firmly it was said.</p>
    </div>

    <div class="finding">
      <h4>2. Two claims from one video, resolved against contradictory findings<span class="sev sev--high">high</span></h4>
      <p>Panel 2 claim 4 is graded <em>bad</em> because tech did <em>not</em> underperform the
      S&amp;P in 2025&ndash;26. Panel 2 claim 5&rsquo;s rationale, four inches down the same page,
      states that &ldquo;the conditional &lsquo;significant tech unwind vs S&amp;P 500&rsquo;
      materialized in March 2026&rdquo; and grades <em>good</em>. The analyst is penalised and
      credited for opposite readings of the same event.</p>
      <p><strong>Cause:</strong> one Claude call per claim with no shared state, which is the right
      default for cost and context, but it means nothing checks a source&rsquo;s resolutions against
      each other. <strong>Fix:</strong> a cheap cross-claim consistency pass over one source&rsquo;s
      resolutions before persisting: the same self-consistency idea the sibling project
      applies <em>within</em> a single evaluation, applied across a source&rsquo;s claim set.</p>
    </div>

    <div class="finding">
      <h4>3. The unit of a claim is not consistent<span class="sev sev--high">high</span></h4>
      <p>The batch splits and merges by opposite rules. Panel 4 claims 6&ndash;10 split one sentence
      listing five holdings into five claims; panel 0 claims 4&ndash;6 split one sentence into three.
      Meanwhile panel 1 claim 1 packs a blowoff top, a bear market, a global recession, asset-price
      deflation and a lost decade into a single claim with a single verdict, and panel 1 claim 13
      requires stocks <em>and</em> Bitcoin <em>and</em> metals to top together. Bitcoin&rsquo;s
      leg was right, and the analyst got nothing for it.</p>
      <p><strong>Fix:</strong> state the rule in the prompt as one asset and one outcome per claim,
      and split composite outcomes the same way multi-asset sentences are already split. The
      splitting machinery already works; it just isn&rsquo;t applied to the outcome side.</p>
    </div>

    <div class="finding">
      <h4>4. Mutually exclusive claims aren&rsquo;t linked<span class="sev sev--med">medium</span></h4>
      <p>Panel 1 claims 5 and 6 are the analyst&rsquo;s explicit either/or on Bitcoin. Keeping both
      is correct. But claim 5 is <em>bad</em> and claim 6 is <em>still pending</em>, so a rollup will
      count one miss and one open call from a single hedged fork, and if both ever resolve,
      the analyst is guaranteed exactly one wrong.</p>
      <p><strong>Fix:</strong> a <span class="mono">claim_group_id</span> plus a mutual-exclusion
      flag, set at extraction time when the analyst frames scenarios as alternatives. Stage 3 then
      scores the group once instead of scoring each branch.</p>
    </div>

    <div class="finding">
      <h4>5. The target window doubles as the price baseline<span class="sev sev--med">medium</span></h4>
      <p><span class="mono">preview_pipeline.py</span> sets
      <span class="mono">start = claim.target_window_start or published_at</span> and fetches prices
      from there, so for any claim whose window opens in the future the return is silently re-based.
      Panel 0 claim 2 (&ldquo;golden crosses lead the market higher over the next 6&ndash;12
      months&rdquo;) was graded on the Jan&rarr;Jul 2026 return, discarding the first six months of
      the move it was meant to judge. It came out <em>good</em> either way, which is exactly why this
      would be easy to miss in production.</p>
      <p><strong>Fix:</strong> separate <span class="mono">measurement_baseline_date</span> (normally
      the publish date) from <span class="mono">target_window_start</span> (when the outcome becomes
      judgeable). Also reject <span class="mono">target_window_start &lt; published_at</span>: 
      panel 2 claim 2 has a window opening nearly three months before the video existed.</p>
    </div>

    <div class="finding">
      <h4>6. Early and late grading are both happening, unrecorded<span class="sev sev--med">medium</span></h4>
      <p>Panel 3 claim 6 was resolved <em>bad</em> with 2.4 years left on its window, while panel 3
      claim 2 on a comparable multi-year window was correctly held pending, two different rules
      inside one source. In the other direction, panel 1 claim 8 was graded <em>good</em> on evidence
      its own rationale places two to four weeks <em>after</em> the window closed.</p>
      <p><strong>Fix:</strong> make it an explicit decision rather than a judgement call. If the
      analyzer grades outside a window, it should have to say so in a field, not just in prose.</p>
    </div>

    <div class="finding">
      <h4>7. The pass/fail standard changes between claims<span class="sev sev--med">medium</span></h4>
      <p>Dominion Energy returned +1.6% against SPY&rsquo;s +5.6% and scored <em>good</em>; XLI
      returned +16.8% against SPY&rsquo;s +24.0% and scored <em>bad</em>. Both are defensible readings
      of the respective wordings (&ldquo;perform well&rdquo; vs &ldquo;be outperformers&rdquo;), but
      the output doesn&rsquo;t record which standard was applied, so the two verdicts are not
      comparable, and stage 3 will average them together.</p>
      <p><strong>Fix:</strong> an <span class="mono">evaluation_basis</span> field on
      <span class="mono">ClaimResolution</span> (<span class="mono">absolute</span> vs
      <span class="mono">relative-to-benchmark</span>), set by the analyzer from the claim&rsquo;s own
      wording.</p>
    </div>

    <div class="finding">
      <h4>8. Third-party estimates are credited to the analyst<span class="sev sev--med">medium</span></h4>
      <p>Panel 3 claim 1 quotes &ldquo;the tax Foundation estimates that the average tariff rate&hellip;
      could rise to nearly 17.7%&rdquo; and scores it as the analyst&rsquo;s <em>good call</em>. Panel
      3 claim 2 does the same with &ldquo;estimates currently suggest&hellip;&rdquo;. An analyst who
      accurately relays other people&rsquo;s forecasts builds a track record they didn&rsquo;t earn
, and this cuts the other way too when a cited forecast misses.</p>
      <p><strong>Fix:</strong> the same <span class="mono">conviction</span> field from finding 1,
      with a <span class="mono">cited</span> value; or a separate
      <span class="mono">is_own_assertion</span> boolean. Either way the prompt needs an explicit
      instruction, because the transcript signal (&ldquo;X estimates that&hellip;&rdquo;) is
      unmistakable and is currently being dropped.</p>
    </div>

    <div class="finding">
      <h4>9. Three quotes are paraphrases presented as verbatim<span class="sev sev--low">low</span></h4>
      <p>All three are in panel 1, the longest transcript, and none distorts the meaning, 
      e.g. &ldquo;&hellip;a lot worse than the data suggests&rdquo; for the actual &ldquo;&hellip;a lot
      worse than they are letting on&rdquo;, and &ldquo;that is when the stock market tops out&rdquo;
      for &ldquo;the top is already in&rdquo;. Low severity on substance, but
      <span class="mono">supporting_quotes</span> is the field a human reviewer trusts to check
      everything else, so drift here is worth watching as transcripts get longer. A fourth
      &ldquo;missing&rdquo; quote turned out to be a legitimate ellipsis stitch of two real
      fragments.</p>
      <p><strong>Fix:</strong> cheap and mechanical: validate each returned quote as a
      substring of the source at extraction time and re-ask for the ones that fail. No prompt
      redesign needed.</p>
    </div>

    <div class="finding">
      <h4>10. Horizon labels drift from their own definitions<span class="sev sev--low">low</span></h4>
      <p>Four claims are tagged <span class="mono">short-term</span> (schema: &ldquo;days to a few
      weeks&rdquo;) on windows of 62, 84, 150 and 181 days. This matters more than it looks:
      <span class="mono">CLAUDE.md</span>&rsquo;s MVP scope deliberately deprioritises short-term
      calls and targets the 1&ndash;12 month swing zone, so a mislabelled horizon puts a claim in the
      wrong bucket for the product&rsquo;s core filter.</p>
      <p><strong>Fix:</strong> a validation check that the horizon band and the computed window
      length agree, and a re-ask when they don&rsquo;t.</p>
    </div>

    <div class="finding">
      <h4>11. Degenerate benchmarks<span class="sev sev--low">low</span></h4>
      <p>Panel 1 claim 1 and panel 4 claim 1 are <span class="mono">^GSPC</span> claims benchmarked
      against SPY. Both report the claim asset and the benchmark at the identical return
      (&minus;4.0% and +4.7%) and then label the result &ldquo;trailed benchmark&rdquo;. Harmless
      here, actively misleading in a UI that shows a beat/trail chip.</p>
      <p><strong>Fix:</strong> in <span class="mono">_benchmark_ticker</span>, return null when the
      benchmark resolves to the claim&rsquo;s own asset, and make
      <span class="mono">beat_benchmark</span> null on a tie rather than false.</p>
    </div>

    <div class="finding">
      <h4>12. The claim/stance boundary leaks both ways<span class="sev sev--low">low</span></h4>
      <p>&ldquo;Gold continues to look like it has topped for me&rdquo; (panel 1) is filed as bearish
      <em>sentiment</em>, so it is never graded, but it is a falsifiable directional call, and
      filing it as a stance means the analyst can never be wrong about it. In the other direction,
      panel 4&rsquo;s five holdings and panel 2&rsquo;s five positions each generate both a claim and a
      stance from the identical sentence. Panel 3&rsquo;s three &ldquo;long&rdquo; stances are worse:
      they come from &ldquo;we&hellip; have been able to benefit&hellip; over the last year by having
      long exposure&rdquo;, a statement about the <em>past</em>, recorded as current positions.</p>
      <p><strong>Fix:</strong> the tense point is a one-line prompt instruction. The
      claim-vs-stance boundary needs a sharper rule than &ldquo;falsifiable&rdquo; alone: 
      &ldquo;X has topped&rdquo; is falsifiable and is currently landing on the wrong side.</p>
    </div>

  </div>
</section>

<section>
  <h3>Where I&rsquo;d put the effort</h3>
  <div class="findings">
    <div class="finding">
      <h4>One schema change unlocks most of the value</h4>
      <p>Findings 1, 8 and part of 3 are all the same missing field. A
      <span class="mono">conviction</span> enum on <span class="mono">ClaimExtraction</span>
 (base-case, hedged, risk-flagged, cited) would let stage 3 stop treating
      &ldquo;the Fed cuts 25bp on December 10&rdquo; and &ldquo;a dip wouldn&rsquo;t surprise
      us&rdquo; as equivalent evidence about an analyst. It changes nothing about what gets
      extracted, which is the part that already works.</p>
    </div>
    <div class="finding">
      <h4>Two of these are mechanical, not prompt work</h4>
      <p>Quote-substring validation (finding 9) and the horizon/window agreement check (finding 10)
      are both deterministic post-parse validations with a re-ask on failure. Same for rejecting a
      window that opens before the publish date (finding 5) and null benchmarks on self-comparison
      (finding 11).</p>
    </div>
    <div class="finding">
      <h4>Panel 1 claim 10 belongs in a fixture file</h4>
      <p>&ldquo;The Fed cuts by another 25bp by December 10&rdquo; (named event, exact date,
      exact magnitude, unambiguous resolution) is what a well-formed claim looks like end to
      end. It is a good regression anchor for any prompt or model change, alongside panel 1 claims
      5/6 for the no-collapse behaviour.</p>
    </div>
  </div>
</section>
</div>"""

_REVIEW_TAB = ('<button class="tab-btn active" onclick="showTab(0)">'
               '<span class="tab-label">Extraction review</span>'
               '<span class="tab-meta">42 claims &middot; 12 findings</span>'
               "</button>")
_REVIEW_TAB_PLACEHOLDER = "<!--REVIEW-TAB-->"


def _sev_label(sev: str) -> str:
    return {"sound": "Sound", "minor": "Minor", "issue": "Issue"}[sev]


def _review_block(sev: str, body: str) -> str:
    return (f'<div class="review review--{sev}">'
            f'<span class="review-tag">{_sev_label(sev)}</span>{body}</div>')


def _annotate_claims_section(section: str, panel_index: int) -> str:
    """Append a review block inside each claim card of one panel's Claims <section>."""
    chunks = section.split('<div class="card">')
    out = [chunks[0]]
    for i, chunk in enumerate(chunks[1:], start=1):
        note = CLAIM_NOTES.get((panel_index, i))
        if note is None:
            out.append(chunk)
            continue
        # The card ends at its final </div>; insert just before it.
        cut = chunk.rstrip().rfind("</div>")
        if cut == -1:
            out.append(chunk)
            continue
        out.append(chunk[:cut] + _review_block(*note) + chunk[cut:])
    return '<div class="card">'.join(out)


def annotate(src: str) -> str:
    if MARKER in src:
        raise SystemExit("error: this file already carries an injected review. Re-run "
                         "preview_batch.py for a clean report, or edit the notes in place.")

    panels = re.findall(r'<div class="panel(?: active)?">.*?(?=<div class="panel|\s*</div>\s*</div>\s*<script)',
                        src, re.S)
    if len(panels) != 5:
        raise SystemExit(f"error: expected 5 source panels, found {len(panels)}; the report "
                         "layout changed; re-check this script against preview_batch.py.")

    for pi, panel in enumerate(panels):
        new_panel = panel
        # 1. per-claim review notes (first <section> of a panel is Claims)
        m = re.search(r"<section>\s*<h3>Claims .*?</section>", new_panel, re.S)
        if m:
            new_panel = new_panel.replace(m.group(0), _annotate_claims_section(m.group(0), pi), 1)
        # 2. per-source summary, inserted directly after the header block
        summary = PANEL_SUMMARIES.get(pi)
        if summary:
            block = f'\n<section>\n  <h3>Extraction review</h3>\n  <div class="finding">{summary}</div>\n</section>\n'
            hm = re.search(r'<div class="header">.*?</div>\s*</div>', new_panel, re.S)
            if hm:
                new_panel = new_panel.replace(hm.group(0), hm.group(0) + block, 1)
        src = src.replace(panel, new_panel, 1)

    # 3. leading review tab + panel, then renumber every showTab() to match DOM order
    src = src.replace("<style>", "<style>" + _REVIEW_CSS, 1)
    src = src.replace('<div class="panel active">', '<div class="panel">', 1)
    # Insert a placeholder first so demoting the old first tab can't also demote the new one.
    src = re.sub(r'(<h1>Sources \(\d+\)</h1>\s*)', r"\1" + _REVIEW_TAB_PLACEHOLDER + "\n    ", src, count=1)
    src = src.replace('<button class="tab-btn active" onclick', '<button class="tab-btn" onclick', 1)
    src = src.replace(_REVIEW_TAB_PLACEHOLDER, _REVIEW_TAB, 1)
    src = re.sub(r'<div class="panels">\s*', '<div class="panels">\n    ' + _REVIEW_PANEL + "\n", src, count=1)
    src = src.replace('<h1>Sources (5)</h1>', '<h1>Review + 5 sources</h1>', 1)

    counter = iter(range(100))
    src = re.sub(r'onclick="showTab\(\d+\)"', lambda _: f'onclick="showTab({next(counter)})"', src)

    return src.replace("</body>", MARKER + "\n</body>", 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="Batch HTML file produced by preview_batch.py.")
    ap.add_argument("--out", default=None, help="Write here instead of editing in place.")
    args = ap.parse_args()

    src_path = Path(args.path)
    out_path = Path(args.out) if args.out else src_path
    out_path.write_text(annotate(src_path.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Review injected into {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
