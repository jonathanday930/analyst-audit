# Analyst test set

A curated list of finance/stock/crypto YouTubers and specific videos for testing the
claim-finder, stance-extractor and claim-analyzer pipelines. This is not wired into the app in
any way; the app has no channel/feed tracking by design (see `../CLAUDE.md`, "Onboarding a new
analyst"). Each video URL below is meant to be pasted individually through the Add-link flow, or
fed directly to a claim-finder prompt during prompt/model testing.

## Selection criteria

- **Horizon**: medium to long range. Calls that play out over roughly 3 to 12 months, not
  intraday or weekly swing trades. Channels whose output is mostly short-term trade calls were
  deliberately excluded (see "Removed / bench" below).
- **Prominence**: subscriber counts run from 410K to 2.73M. No small channels.
- **Resolvability**: every "primary" video below is **over a year old** (published between Oct
  2024 and Jun 2025), so its 3-to-12-month claims have already fully resolved. That makes them
  usable as end-to-end ground truth for claim analyzer, not just extraction fixtures.
- **Mechanics**: every video listed below was checked to have caption tracks available, so the
  YouTube transcript path will work.
- **Runtime**: each channel carries a **short pick**, the shortest video on that channel that
  still holds real claims, for when a fast extraction test is wanted instead of a full one. Three
  channels have no genuinely short format: Coin Bureau bottoms out near 17 minutes, Joseph
  Carlson near 16, and Peter Schiff jumps straight from sub-5-minute clips to hour-long podcasts.
  Runtimes are listed on every entry.

## How this list was verified

Every video id below was fetched from its YouTube watch page and the **channel name, exact
title, upload date, and caption availability were read off the page itself**, not inferred from
search snippets. Claim summaries are still leads based on titles and search coverage, not
extracted claims, so treat the "what to expect" notes as hints and not as answer keys.

## Ground truth anchors (for scoring the older videos)

Useful context when judging whether a late-2024 / early-2025 call was right:

- Bitcoin peaked at an all-time high of about **$126,198 on Oct 6, 2025**, then fell hard through
  2026: roughly **$60K on Feb 6, 2026**, and a 21-month low near **$58K in late June 2026**, a
  drawdown of over 50% from the top.
- The **S&P 500 finished 2025 up about 16%** (about 17.4% with dividends), so 2025 crash calls
  are cleanly falsifiable.

## The 10 channels

Ordered by subscriber count. Counts read from each channel page in Sep 2026.

### 1. Coin Bureau (2.73M) - crypto

https://www.youtube.com/@CoinBureau
The largest crypto-education and weekly-market-analysis channel. Long-form, research-flavored,
usually gives explicit price ranges and named catalysts. Guy Turner.

- **"2025 Crypto Predictions - Coin Bureau's Insider Breakdown!"** - 2024-12-29 - 20:23 - 207K views
  https://www.youtube.com/watch?v=8HvSFVJgXNQ
  A whole year of bundled predictions published right before the window it predicts. Best single
  multi-claim extraction fixture in the set.
- **"Bitcoin Price Prediction 2025: $200K, $300K... or $1M?"** - 2025-06-01 - 21:03 - 68K views
  https://www.youtube.com/watch?v=QjH-wvXpz-4
  Explicit numeric BTC targets with a stated horizon. BTC topped at $126K, so these resolve
  cleanly as too-high.
- **Short pick: "ETH Price Prediction 2025: Is $10K Ethereum Possible?"** - 2024-12-17 - 18:35 - 268K views
  https://www.youtube.com/watch?v=3OMQwXBhajc
  A named number in the title on a single asset. Note that Coin Bureau's runtime floor is about
  17 minutes, so this is the shortest usable option rather than a true 10-minute video.

### 2. New Money (1.09M) - equities, long-term

https://www.youtube.com/@NewMoneyYouTube
Brandon van der Kolk. Long-horizon business analysis and valuation, heavy on 13F/"smart money"
tracking. Very few short-term calls, which makes it a good contrast case.

- **"The Smart Money's Biggest Bets for 2025 Revealed"** - 2025-03-24 - 15:29 - 118K views
  https://www.youtube.com/watch?v=VemoFTfeCnY
  Several named tickers framed as year-ahead positioning.
- **"The Truth About Nvidia Stock."** - 2025-02-23 - 14:46 - 127K views
  https://www.youtube.com/watch?v=phtxTKBoZ5o
  Single-ticker valuation thesis. Good test of whether claim finder can pull a falsifiable claim
  out of a mostly-analytical video with no headline price target.
- **Short pick: "Stock Market History is Repeating Itself."** - 2025-02-10 - 14:27 - 496K views
  https://www.youtube.com/watch?v=sbZEPQBjYXg
  His own macro thesis rather than a 13F recap, which is what most of his shorter videos are.
  Useful precisely because the claim has to be dug out of an analogy.

### 3. Benjamin Cowen / Into The Cryptoverse (1.01M) - crypto, quant

https://www.youtube.com/@benjaminjcowen
Data-driven cycle timing, log regression bands, risk metrics. Makes dated, conditional,
model-backed calls, which is close to the ideal shape for the claim schema.

- **"Bitcoin Dominance in 2025"** - 2025-01-23 - 1:15:05 - 124K views
  https://www.youtube.com/watch?v=8nBbg72z-PI
  Long-form, heavily conditional ("if X then Y by Z"). Strong test of the schema rule that each
  distinct condition+outcome pair becomes its own claim rather than collapsing to a base case.
- **"NFA Live! Bitcoin in 2025"** - 2025-06-26 - 49:20 - 38K views
  https://www.youtube.com/watch?v=LUx9UCDGDsY
  Mid-year update on the same thesis. Pairs with the video above to test whether a restated or
  revised thesis is tracked consistently over time.
- **Short pick: "S&P 500 Outlook"** - 2024-12-21 - 13:43 - 49K views
  https://www.youtube.com/watch?v=NtbnoQdc7sY
  Cowen off the crypto beat, applying the same model-driven framing to equities. Short, dated,
  and directly comparable to the equities channels in the set.

### 4. Tom Nash (689K) - equities

https://www.youtube.com/@TomNashTV
Single-stock deep dives plus macro reaction videos. Blunt directional language and frequent
explicit targets, so extraction should be easy and scoring should be decisive.

- **"The 2025 Stock Market Crash Just Started"** - 2025-02-23 - 12:27 - 213K views
  https://www.youtube.com/watch?v=t5ssiP5gahg
  A dated crash call. The S&P finished 2025 up ~16%, so this resolves clearly against him and is
  a good negative-verdict fixture.
- **"ANET Stock - The Investment Opportunity of a Lifetime"** - 2025-06-05 - 16:30 - 180K views
  https://www.youtube.com/watch?v=8IINb0z0OP0
  Single-ticker long thesis with a 12-month-plus horizon.
- **Short pick: "Palantir Earnings Recap [Revealing My New 5 Year Price Target]"** - 2025-08-04 - 12:33 - 125K views
  https://www.youtube.com/watch?v=tlogQIhTX_U
  An explicit, self-authored, numbered price target with a stated horizon in the title. About as
  clean as a single claim gets.

### 5. Bravos Research (641K) - macro / technical

https://www.youtube.com/@bravosresearch
Macro plus technical analysis across equities, gold, commodities and rates. Multi-month theses
restated across videos, which is exactly the repeated-claim case stage 3 needs to handle.

- **"« This Time is Different »"** - 2025-01-03 - 8:12 - 227K views
  https://www.youtube.com/watch?v=JgCVaVxFv_0
- **"This Just Changed Everything For 2025..."** - 2025-01-17 - 6:57 - 139K views
  https://www.youtube.com/watch?v=P-ts9UQQiT0
- **"Gold is Predicting Another Major Economic Crisis."** - 2025-03-26 - 7:55 - 123K views
  https://www.youtube.com/watch?v=7rwtEi1S168
  Three videos over three months on an overlapping thesis. Use together to test claim
  deduplication and thesis-drift tracking.
- **Short pick: "In 5 Months This Will All Be Over."** - 2025-06-12 - 8:43 - 571K views
  https://www.youtube.com/watch?v=470oRsDElYU
  A hard five-month window stated up front, at 8:43. The best short fixture in the whole set,
  and the closest thing here to a textbook condition+outcome+window claim.

### 6. Peter Schiff (635K) - macro, gold, dollar

https://www.youtube.com/@peterschiff
Long-running podcast. Persistent, unusually explicit macro stances (dollar, gold, inflation,
crash timing) that he restates for years. The single best channel here for testing the
"open-ended stance with no target window" path and the stance/sentiment extractor.

- **"Will 2025 Be the Year the Bubbles Finally Burst? - Ep 1001"** - 2024-12-27 - 56:57 - 104K views
  https://www.youtube.com/watch?v=dU47vCFWVPI
  Year-ahead framing, mostly macro conditions rather than price levels.
- **"Stagflation: The Fed's Worst Nightmare Is Coming True - Ep 1008"** - 2025-02-07 - 58:47 - 93K views
  https://www.youtube.com/watch?v=EdP8JiyOFAY
- **"A Worse Financial Crisis Than 2008 Is the Only Road to Recovery"** - 2025-06-19 - 4:55 - 98K views
  https://www.youtube.com/watch?v=6qmbBYukMY4
  Short-form version of a long-held stance. Good test that a stance with no window is recorded
  as a stance and never enters the resolve loop.
- **Short pick: "The Truth Behind China's Tariffs and Gold's Price Surge"** - 2025-04-15 - 4:34 - 84K views
  https://www.youtube.com/watch?v=Sxda2mTXEFA
  Schiff has no middle length: the podcast runs 45 to 70 minutes and the clips run under 5. This
  is the short end. Good for testing that a thin, single-topic source does not get over-extracted.

### 7. George Gammon (582K) - macro

https://www.youtube.com/@GeorgeGammon
Note: this is Gammon's main channel. The older test set pointed at
`@RebelCapitalistChannel` (209K), which is his secondary channel. Use `@GeorgeGammon`.
Rates, liquidity, recession indicators. Almost no single-ticker calls, so it is the right
channel for exercising real-world-event and macro-condition claims that need the web-search
resolution path rather than price data.

- **"2025 Inflation Prediction (I've Changed My Mind)"** - 2025-01-24 - 22:01 - 138K views
  https://www.youtube.com/watch?v=n1GWENcljqc
  An explicit dated macro forecast, and framed as a revision of a prior view, so it doubles as a
  walk-back test case.
- **"The Fed's #1 Recession Indicator Was JUST Triggered"** - 2025-02-28 - 26:51 - 119K views
  https://www.youtube.com/watch?v=LTmbmtqLh4M
- **"Huge Wall St Firm Predicts US CRISIS By June"** - 2025-04-30 - 19:31 - 154K views
  https://www.youtube.com/watch?v=ELpMg8NQorA
  A named deadline ("by June") on a real-world event. Good claim-analyzer fixture, and a good
  test that a forecast he is *reporting* from someone else is not attributed to him as his own
  claim.
- **Short pick: "Should You Still Be Worried About A Recession?"** - 2025-04-16 - 13:50 - 67K views
  https://www.youtube.com/watch?v=3_BxbHRGx4w
  A direct macro-condition question with his own answer, no third-party forecast to disentangle.
  The plain counterpart to the attribution trap above.

### 8. InvestAnswers (577K) - crypto / macro, quant

https://www.youtube.com/@InvestAnswers
Model-driven numeric targets (M2 money supply, supply-flow models) with stated timeframes.
Consistently the most numerically explicit channel in the set.

- **"My 2025 Crypto, Market & Macro Predictions"** - 2024-12-27 - 20:57 - 172K views
  https://www.youtube.com/watch?v=LPK7FD781S0
  Year-ahead multi-asset predictions with numbers attached.
- **"2025 Bitcoin Expert Price Predictions Analyzed"** - 2025-01-01 - 21:16 - 112K views
  https://www.youtube.com/watch?v=-P8xQsEKCgk
  He analyzes *other people's* predictions here. Deliberately included as an attribution test:
  the pipeline should not record third-party targets as his own claims.
- **Short pick: "Bitcoin Bear, Base, and Bull Case for 2025"** - 2024-12-28 - 14:42 - 82K views
  https://www.youtube.com/watch?v=TjupBwZF5pg
  Three explicitly separate scenarios in one video. The sharpest available test of the schema
  rule that scenarios are never collapsed into a single base case.

### 9. Joseph Carlson (511K) - equities, long-term

https://www.youtube.com/@JosephCarlsonShow
Dividend-growth and quality-compounder investing with a public real-money portfolio. Buy
decisions come with valuation anchors, and the multi-year horizon is a useful contrast to the
crypto channels.

- **"Top 10 Stocks To Buy Today"** - 2025-01-10 - 48:54 - 257K views
  https://www.youtube.com/watch?v=6JwSSHaObUk
  Ten named tickers in one video. The heaviest multi-claim-per-video fixture here.
- **"The Four Deepest Value Stocks In The Market"** - 2025-03-20 - 25:44 - 137K views
  https://www.youtube.com/watch?v=VBYqbfLgcTw
- **"Five Quality Stocks To Buy Now"** - 2025-05-27 - 28:49 - 158K views
  https://www.youtube.com/watch?v=tA_WS8Aeclo
- **Short pick: "5 Stocks To Buy And Hold Forever"** - 2024-10-17 - 16:31 - 585K views
  https://www.youtube.com/watch?v=j9OHzRypRVs
  Five named tickers at his shortest runtime. Carlson's floor is about 16 minutes; the main show
  runs 25 to 50.

### 10. Everything Money (410K) - value equities

https://www.youtube.com/@EverythingMoney
Paul Gabrail. Intrinsic/fair-value framework with explicit "buy under $X" targets, which map
almost directly onto the claim schema's condition+outcome shape.

- **"The 2025 Stock Market Crash Will Make Millionaires (HERE'S HOW)"** - 2025-03-15 - 12:42 - 83K views
  https://www.youtube.com/watch?v=eG5Yt25mrVE
- **"I Picked 7 Stocks To Beat The Market in 2025 (Update)"** - 2025-04-21 - 19:49 - 47K views
  https://www.youtube.com/watch?v=Kj-D7fmvcVs
  Seven named tickers with a stated benchmark to beat and a stated year. Cleanest scoreable
  fixture in the whole set, and framed as an update to an earlier call.
- **Short pick: "Why SCHD is Really Crashing in 2025 - Sell NOW or Buy More?"** - 2025-04-28 - 10:24 - 121K views
  https://www.youtube.com/watch?v=BFzkfFgkU6o
  A single instrument, a binary sell-or-buy decision, and a stated year, in 10 minutes flat. The
  closest video in the set to the requested shape.

## Removed / bench

### Removed from the primary set

- **Camel Finance** (@camelfinance, 40.7K) - removed. Fails both bars: far too small to count as
  prominent, and the content is short-horizon swing trading and live trade posts.
- **Meet Kevin** (@MeetKevin, 2.05M) - removed from the primary set. Prominent enough, but the
  output is high-frequency short-term reaction commentary, several videos a day. Keep on the
  bench if a high-volume, low-horizon analyst is ever wanted as a contrast case.
- **Dumb Money Live** (@DumbMoneyLive, 211K) - removed. Chris Camillo's social-arbitrage horizon
  is a good fit conceptually, but the channel's back catalogue over a year old is almost entirely
  livestreams and Shorts, with no searchable long-form prediction videos. Not practical as a
  transcript fixture source.

### Bench (verified, held in reserve)

- **Altcoin Daily** (@AltcoinDaily, 1.66M) - crypto. Held back only because crypto is already
  three of the ten. Verified fixtures if wanted:
  - "Why Bitcoin Price Hits 200k in 2025 (Explained in Under 10 Minutes)" - 2024-10-28 -
    https://www.youtube.com/watch?v=LhokaIIbv7A
  - "My 2025 Bitcoin Price Prediction (with sell targets)" - 2025-01-02 -
    https://www.youtube.com/watch?v=aoreysfoP1o

Other prominent long-horizon channels found but not yet fixture-verified: ARK Invest
(@ARKInvest2015, 640K, multi-year price targets), Stansberry Research (@StansberryMedia, 570K),
Value Investing with Sven Carlin (@Value-Investing, 270K).

## Corrections to the previous version of this file

The earlier version of this list was assembled from search snippets and was not verified against
the video pages. Checking every id turned up substantial errors, which is why the whole file was
rebuilt. Recorded here so the same mistakes are not repeated:

- `6OK5nFeZtXc` ("My Bitcoin and Altcoin Plans Going into 2026") was attributed to InvestAnswers.
  It is actually **VirtualBacon**.
- `L634fvorepU` ("Why The Stock Market In 2026 Is Easy Money") was attributed to Everything
  Money. It is actually **Kyle Livingston**.
- `fhgZms8iN1w` ("I F*ked Up... My INSANE Stock Market Prediction For 2026") was attributed to
  Everything Money. It is actually **Graham Stephan**.
- `MAhMXz6eTIQ` ("Top Stock Picks for 2026") was attributed to Dumb Money Live. It is actually
  **valuetrendcanada**.
- `g51CsNFZWC0` ("Will The Economy Slow Or Grow In 2026?") was attributed to George Gammon's own
  channel. It is a **Thoughtful Money / Adam Taggart** interview *featuring* Gammon. Still usable,
  but the analyst attribution has to be the guest, not the channel.
- `TTn3RN6fuU8` was attributed to Meet Kevin's channel. It is **The Iced Coffee Hour** with Kevin
  as guest. Same guest-vs-channel issue.
- `kU0X-Btolu0` ("The 2026 Stock Market Crash is Coming!") was attributed to Meet Kevin. It is
  actually **Everything Money**.
- `zwcqoGsDyMo` was listed as Bravos Research's "6 Stocks with Largest Upside in 2026". The
  channel is right but the actual title is **"Brace Yourself."** (2026-03-03).
- `xSyKDOHmqL4` (listed under George Gammon) is **no longer available**.

The guest-vs-channel cases above are worth keeping in mind generally: an interview channel is
not the analyst, and the pipeline needs the guest recorded as the claim's author.

## Recent videos (under a year old, claims not yet resolved)

Kept separately because they are useful for extraction testing but cannot be scored yet. All
verified.

- Bravos Research, "Brace Yourself." - 2026-03-03 - https://www.youtube.com/watch?v=zwcqoGsDyMo
- Bravos Research, "History is About to Be Made." - 2026-05-01 - https://www.youtube.com/watch?v=YUwjueXzffE
- Bravos Research, "Your Last Chance at Generational Wealth." - 2026-05-15 - https://www.youtube.com/watch?v=7830S4NkFe8
- Coin Bureau, "Bitcoin's Next KEY MOVE, Huge 2026 Crypto Predictions, Metal Squeeze & More!" -
  2025-12-29 - https://www.youtube.com/watch?v=R5R10Ivm2c8
- Everything Money, "The 2026 Stock Market Crash is Coming! (DO THIS NOW)" - 2026-03-31 -
  https://www.youtube.com/watch?v=kU0X-Btolu0
