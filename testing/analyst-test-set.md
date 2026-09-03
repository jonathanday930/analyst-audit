# Analyst test set

A curated starting list of finance YouTubers and specific videos to use once the claim-finder
pipeline is built, for testing extraction quality across models. This is not wired into the app
in any way; the app has no channel/feed tracking by design (see `../CLAUDE.md`, "Onboarding a
new analyst"). Each video URL below is meant to be pasted individually through the Add-link flow
once it exists, or fed directly to a claim-finder prompt during prompt/model testing.

Videos were picked for having clear, falsifiable, dated predictions (a price level, a named
event, or a stated timeframe), per the claim schema in `../CLAUDE.md`. Publish dates are
approximate, pulled from search results, not verified against the video page itself.

## The 3 requested channels

### Bravos Research
https://www.youtube.com/@BravosResearch
Macro/technical-analysis channel, trade ideas across commodities, energy infrastructure,
uranium, base metals. Runs a paid membership tier for deeper reports.

- "6 Stocks with Largest Upside in 2026" - https://www.youtube.com/watch?v=zwcqoGsDyMo - Mar 3, 2026
  Names 6 specific stocks with largest expected 2026 upside; clean per-ticker claims.
- "History is About to Be Made." - https://www.youtube.com/watch?v=YUwjueXzffE - ~May 1, 2026
  Reiterates/updates the same research report; good test of whether extraction treats a
  restated thesis consistently over time.
- "Your Last Chance at Generational Wealth." - https://www.youtube.com/watch?v=7830S4NkFe8 - ~May 15, 2026
  Same thesis again, a third data point on the same underlying calls.

### Camel Finance
https://www.youtube.com/@camelfinance
Independent/retail trader (grew roughly 1k to 15k subscribers in about a year), swing trades
plus a Bitcoin 4-year-cycle theory, posts live trades, sells a "CF Cycle Trading Indicator."

- "New Lows are Coming for Bitcoin" - https://www.youtube.com/watch?v=bTPOF33F1EQ - May 18, 2026
  BTC to make new cycle lows; directional plus timing claim.
- "Nearly at Target" - https://www.youtube.com/watch?v=8MrQKGb6zrs - Jun 2, 2026
  BTC approaching a specific cycle price target; also touches on Saylor/MicroStrategy selling.
- "Bitcoin: Ready to Bounce?" - https://www.youtube.com/watch?v=pSgiugWPm8s - May 26, 2026
  Short-horizon bounce call, a useful contrast to the other two videos' longer cycle calls.

### Dumb Money Live
https://www.youtube.com/@DumbMoneyLive
Chris Camillo ("Laughing at Wall Street," Social Arbitrage strategy) with Dave Hanson and
Jordan McLain. Real-money picks sourced from consumer/cultural trend-spotting.

- "Top Stock Picks for 2026: 4 Big Ideas Revealed!" - https://www.youtube.com/watch?v=MAhMXz6eTIQ - early 2026
  4 distinct named picks in one video; good multi-claim-per-video test case.
- "SpaceX IPO: Get Rich or Get Wrecked" - https://www.youtube.com/watch?v=15pYsQ-BN-s - Jun 9, 2026
  Bull/bear stance on SpaceX's IPO; event-conditioned rather than a plain price level.
- "GTA 6 Launch Trade: Boom or Bust for Take Two?" (TTWO) - ~Jul 3, 2026 - **URL not confirmed**,
  only the title/date turned up in search. Directional TTWO call tied to a real-world launch
  event, worth tracking down on the channel directly since it's a good real-world-event
  condition test case.

## 7 additional analysts

### Coin Bureau
https://www.youtube.com/@CoinBureau
Large, well-established crypto-education and weekly market-analysis channel.

- "Bitcoin's Next KEY MOVE, Huge 2026 Crypto Predictions, Metal Squeeze & More!" -
  https://www.youtube.com/watch?v=R5R10Ivm2c8 - Dec 29, 2025
  Multiple bundled 2026 crypto predictions in one video, published just before the window it
  predicts; good multi-claim extraction test.

### Benjamin Cowen (Into The Cryptoverse)
https://www.youtube.com/@intothecryptoverse
Data/quant crypto analyst, cycle-timing and log-regression models, large credentialed following.

- Widely reported (BeInCrypto, CoinMarketCap Academy, Yahoo Finance, Bitget, others, Apr 2026):
  Bitcoin's 4-year cycle points to an October 2026 bottom, with an expectation BTC revisits
  ~$60k before any durable recovery. **No specific source video URL confirmed** by search, only
  third-party coverage of his content. Grab the actual video from his channel before using this
  as a seed. A specific $39k figure mentioned in earlier notes did not check out on re-search;
  don't use it.

### Meet Kevin (Kevin Paffrath)
https://www.youtube.com/@MeetKevin
High-frequency, big-personality real estate/stocks/macro commentator (~2M subscribers), known
for bold short-term calls.

- "Stocks Just Hit ANOTHER Record High - WTF Is Happening?!" -
  https://www.youtube.com/watch?v=TTn3RN6fuU8 - 2026
  Reaction to market highs with a forward view.
- "The 2026 Stock Market Crash is Coming! (DO THIS NOW)" -
  https://www.youtube.com/watch?v=kU0X-Btolu0 - Mar 31, 2026 (confirmed on re-search)
  Discusses NASDAQ correction territory, gas prices, and Iran conflict as crash drivers. Pairing
  this with the record-high video above is a good test of the claim schema's rule to record
  distinct, even contradictory, claims separately rather than collapsing to one stance.

### InvestAnswers
https://www.youtube.com/@InvestAnswers
Quant-style crypto/macro analysis, M2 money-supply models, explicit numeric price targets.

- "My Bitcoin and Altcoin Plans Going into 2026" - https://www.youtube.com/watch?v=6OK5nFeZtXc -
  Nov 26, 2025 (confirmed on re-search)
  Short-to-mid-term BTC/altcoin expectations heading into 2026.
- Also reported (DailyHodl): a BTC year-end target of roughly $115k from an M2-supply model;
  source video URL not found, only third-party coverage. Same caveat as Cowen above.

### George Gammon (Rebel Capitalist)
https://www.youtube.com/@RebelCapitalistChannel
Macro/rates-focused, Austrian-economics-influenced, recession/liquidity-cycle calls. Not a
stock-picker, useful for testing real-world-event and macro-condition claims rather than
single-ticker price claims.

- "Will The Economy Slow Or Grow In 2026?" - https://www.youtube.com/watch?v=g51CsNFZWC0
  Explicitly "takes the under" on 2026 GDP growth; states an asymmetry of 10-15% stock upside
  vs. 30-50% downside if labor weakens.
- "What's Coming Is WORSE Than A Recession..." - https://www.youtube.com/watch?v=xSyKDOHmqL4
  Even more bearish macro call, a useful severity/horizon contrast with the video above.

### Joseph Carlson (The Joseph Carlson Show)
https://www.youtube.com/@JosephCarlsonShow
Equities-focused, dividend-growth/long-term portfolio investor.

- "10 Value Stocks To Buy For 2026" (published Dec 16, 2025 per podcast listing) covers Barron's
  10 best stocks for 2026, with Amazon as a top pick at roughly $232, about 29x 2026 earnings,
  citing margin expansion as the main upside driver. **Only podcast-platform listings were found
  (Spotify, Podscan), not the YouTube video itself** - locate the actual video on his channel
  before using. Good long-term/structural-horizon test case with an explicit valuation anchor.

### Everything Money (Paul Gabrail)
https://www.youtube.com/@EverythingMoney
Value-investing education, intrinsic/fair-value stock calls, "buy under $X" framework.

- "Why The Stock Market In 2026 Is Easy Money" - https://www.youtube.com/watch?v=L634fvorepU -
  May 7, 2026
  Bullish 2026 market call, plus the channel's usual specific buy-target prices.
- "I F*ked Up... My INSANE Stock Market Prediction For 2026" -
  https://www.youtube.com/watch?v=fhgZms8iN1w
  Same analyst revisiting and correcting an earlier prediction; a strong test case for how the
  pipeline should handle a analyst's own walk-back of a prior claim.

## Gaps to close before using as real seeds

Three video URLs still need to be tracked down directly from the channel rather than search:
Dumb Money Live's GTA 6/Take-Two video, Benjamin Cowen's October-2026-bottom video, and Joseph
Carlson's 2026 value-stocks video. Everything else above is a confirmed `youtube.com/watch?v=...`
link with a title and approximate date from search results, but none of these have been opened
and read in full, only surfaced via search snippets and video titles, so treat the claim
summaries as leads to verify, not as extracted claims.
