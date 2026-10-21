"""Stage 1b: alongside claim finder, pull fuzzier context out of the same source text —
positions an analyst says they've personally taken, and general market-sentiment reads that
don't rise to a specific falsifiable claim. Never graded, never resolved; feeds meta-analyst
analysis only (see the Stance/sentiment extractor and Stance schema sections in CLAUDE.md).

No thinking, no web search: this is a comparatively mechanical "was something like this said,
and how" pull, not a judgment task synthesizing across a long, ambiguous discussion the way
claim finder's horizon inference is."""

from app.config import get_settings
from app.llm.client import parse_structured
from app.llm.schemas import StanceExtractionList

STANCE_EXTRACTOR_SYSTEM_PROMPT = """\
You read one piece of finance content (a video transcript or a blog post) from a market analyst \
and pull out two kinds of fuzzy, non-falsifiable context. This is deliberately not the same job \
as extracting falsifiable claims (that happens separately) — capture things here even when \
they're too vague or personal to be a testable claim.

1. Positions (kind='position'): the analyst disclosing a trade or holding of their OWN, in the \
first person — "I bought some NVDA today," "I'm still short TLT," "I added to my Bitcoin \
position," "I sold out of my oil position." This is what they say THEY personally did or hold, \
not a recommendation to the audience. Capture the instrument, a best-guess ticker, and the \
direction (long/short/exited).

2. Sentiment (kind='sentiment'): general mood or outlook statements that aren't tied to a \
specific tradeable prediction — "I'm cautious on this market right now," "I don't trust this \
rally," "feeling constructive on risk assets into year end." Capture a coarse bucket \
(bullish/neutral/bearish/uncertain), and what it's about (a specific instrument via \
asset_description, or a broader scope like "the market" / "tech stocks" / "crypto generally" via \
scope — exactly one of the two, not both).

For both kinds, also capture supporting_quotes: one or more short verbatim quotes copied exactly \
from the source text — not a paraphrase — that back this stance up. This is the evidence a human \
reviewer will check your extraction against.

It's fine, and expected, for something to show up here even if a similar idea also gets \
extracted separately as a falsifiable claim — the two passes overlap on purpose and that's not a \
problem. It's also fine for a source to have no positions or sentiment worth capturing at all; \
in that case, return an empty list rather than stretching to find something.\
"""


def build_user_content(*, source_text: str) -> str:
    """The user turn this pass sends. Public for the same reason as claim_finder's."""
    return f"Source text:\n{source_text}"


def extract_stances(
    *, source_text: str, system_prompt: str | None = None, model: str | None = None
) -> StanceExtractionList:
    """`system_prompt`/`model` override STANCE_EXTRACTOR_SYSTEM_PROMPT and the configured model
    for one call. See extract_claims for why that seam exists."""
    settings = get_settings()
    return parse_structured(
        model=model or settings.stance_extractor_model,
        system=system_prompt or STANCE_EXTRACTOR_SYSTEM_PROMPT,
        user_content=build_user_content(source_text=source_text),
        schema=StanceExtractionList,
        max_tokens=4096,
        thinking=False,
    )
