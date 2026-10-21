#!/usr/bin/env bash
# Run the preview batch over every video in ../../testing/analyst-test-set.md whose listed
# runtime is under 20 minutes (21 of the 34 videos in the primary 10-channel set), rendered as
# one tabbed HTML report for manual review of the claims found.
#
# Runtimes come from the test-set file, which recorded them off each YouTube watch page.
# Excluded for length: Coin Bureau 8HvSFVJgXNQ (20:23) and QjH-wvXpz-4 (21:03), Cowen
# 8nBbg72z-PI (1:15:05) and LUx9UCDGDsY (49:20), Schiff dU47vCFWVPI (56:57) and EdP8JiyOFAY
# (58:47), Gammon n1GWENcljqc (22:01) and LTmbmtqLh4M (26:51), InvestAnswers LPK7FD781S0 (20:57)
# and -P8xQsEKCgk (21:16), Carlson 6JwSSHaObUk (48:54), VBYqbfLgcTw (25:44) and tA_WS8Aeclo
# (28:49). The file's "Recent videos" and "Bench" entries carry no recorded runtime, so they are
# not included here.
#
# Usage:
#   cd backend && source .venv/bin/activate
#   scripts/run_short_test_set.sh [extra preview_batch.py args...]
#
# Defaults to --skip-analysis (claim finder + stance extractor only), which is what you want
# when reviewing extraction quality. Pass --with-analysis to also run the claim analyzer.

set -euo pipefail

SKIP_ANALYSIS="--skip-analysis"
EXTRA=()
for arg in "$@"; do
  if [[ "$arg" == "--with-analysis" ]]; then
    SKIP_ANALYSIS=""
  else
    EXTRA+=("$arg")
  fi
done

Y="https://www.youtube.com/watch?v="

python scripts/preview_batch.py \
  --source "${Y}3OMQwXBhajc" "Coin Bureau"        `# 18:35 ETH Price Prediction 2025` \
  --source "${Y}VemoFTfeCnY" "New Money"          `# 15:29 Smart Money's Biggest Bets for 2025` \
  --source "${Y}phtxTKBoZ5o" "New Money"          `# 14:46 The Truth About Nvidia Stock` \
  --source "${Y}sbZEPQBjYXg" "New Money"          `# 14:27 Stock Market History is Repeating Itself` \
  --source "${Y}NtbnoQdc7sY" "Benjamin Cowen"     `# 13:43 S&P 500 Outlook` \
  --source "${Y}t5ssiP5gahg" "Tom Nash"           `# 12:27 The 2025 Stock Market Crash Just Started` \
  --source "${Y}8IINb0z0OP0" "Tom Nash"           `# 16:30 ANET Stock` \
  --source "${Y}tlogQIhTX_U" "Tom Nash"           `# 12:33 Palantir Earnings Recap` \
  --source "${Y}JgCVaVxFv_0" "Bravos Research"    `# 8:12  This Time is Different` \
  --source "${Y}P-ts9UQQiT0" "Bravos Research"    `# 6:57  This Just Changed Everything For 2025` \
  --source "${Y}7rwtEi1S168" "Bravos Research"    `# 7:55  Gold is Predicting Another Major Economic Crisis` \
  --source "${Y}470oRsDElYU" "Bravos Research"    `# 8:43  In 5 Months This Will All Be Over` \
  --source "${Y}6qmbBYukMY4" "Peter Schiff"       `# 4:55  A Worse Financial Crisis Than 2008` \
  --source "${Y}Sxda2mTXEFA" "Peter Schiff"       `# 4:34  China's Tariffs and Gold's Price Surge` \
  --source "${Y}ELpMg8NQorA" "George Gammon"      `# 19:31 Huge Wall St Firm Predicts US CRISIS By June` \
  --source "${Y}3_BxbHRGx4w" "George Gammon"      `# 13:50 Should You Still Be Worried About A Recession` \
  --source "${Y}TjupBwZF5pg" "InvestAnswers"      `# 14:42 Bitcoin Bear, Base, and Bull Case for 2025` \
  --source "${Y}j9OHzRypRVs" "Joseph Carlson"     `# 16:31 5 Stocks To Buy And Hold Forever` \
  --source "${Y}eG5Yt25mrVE" "Everything Money"   `# 12:42 The 2025 Stock Market Crash Will Make Millionaires` \
  --source "${Y}Kj-D7fmvcVs" "Everything Money"   `# 19:49 I Picked 7 Stocks To Beat The Market in 2025` \
  --source "${Y}BFzkfFgkU6o" "Everything Money"   `# 10:24 Why SCHD is Really Crashing in 2025` \
  ${SKIP_ANALYSIS} ${EXTRA[@]+"${EXTRA[@]}"}
