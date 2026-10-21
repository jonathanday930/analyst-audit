"""Stage 3: reads one analyst's whole claim history (raw claims + resolved verdicts), plus
their disclosed stances/sentiment when available, and derives categorization and a
plain-language read of their track record after the fact — see the Meta analyst analysis stage
description in CLAUDE.md. Categorization is deliberately not baked in at claim-finder time so
the scheme can change later without re-extracting anything.

Only assigns categories and writes qualitative summaries — deliberately does NOT compute counts,
ratios, or a numeric reliability score itself. Mirrors `youtube_fact_checker`'s summary step,
which computes its correct/total rollup deterministically in Python rather than asking Claude to
do arithmetic a probabilistic pass could get wrong (see that project's CLAUDE.md, "Request
flow" step 3): here, once this pass labels each claim with a category, the caller does the
tallying against each claim's already-known verdict — that rollup isn't built yet either (see
TASKS.md), but this pass's output is shaped to make it a pure counting step when it is.

No web search — this pass works entirely off history that's already been extracted and graded;
it isn't looking anything up. Uses adaptive thinking: synthesizing consistent categories and
genuine strengths/weaknesses across a long, varied claim history is a real judgment task."""

from app.config import get_settings
from app.llm.client import parse_structured
from app.llm.schemas import AnalystMetaAnalysis, ClaimHistoryEntry, StanceHistoryEntry

META_ANALYST_SYSTEM_PROMPT = """\
You read one finance analyst's full claim history — every falsifiable call they've made and, \
for the ones that have been checked, whether it panned out — and produce a plain-language read \
of their track record, organized by category.

For every claim given, assign it a category label in your own words — group claims that are \
meaningfully alike (same asset class, same kind of call), so a reader can see where this analyst \
is strong versus weak, e.g. "crypto", "macro/rates calls", "individual large-cap tech stocks", \
"options/volatility calls". Don't force claims into a fixed taxonomy; invent categories that fit \
what THIS analyst actually talks about. Do stay consistent within this one analysis — don't \
create two near-duplicate categories for the same kind of claim. Do not compute counts, ratios, \
or scores yourself; just label each claim — the counting happens afterward, outside this call.

If stance/sentiment history is also given, use it as supporting context, not as something to \
grade: it's informal, self-disclosed color (positions they say they've personally taken, general \
market mood) that was never a testable prediction. Use `consistency_notes` to flag anything \
notable about how it lines up (or doesn't) with how their actual graded claims played out — for \
example, an analyst who kept publicly calling for a crash while staying personally long tech \
says something different about their reliability than one whose stated positions matched their \
calls. Leave `consistency_notes` null if no stance history was given, or if nothing notable \
stands out.

Write:
- overall_summary: a few plain-language sentences on this analyst's track record as a whole.
- strengths / weaknesses: short, specific observations tied to what's actually in the data \
(e.g. "consistently right about Fed-driven macro moves") — not generic praise or vague criticism.

Base everything only on the data given. Don't speculate beyond it, and don't let a small number \
of claims in a category support a sweeping conclusion — say so if the sample is thin.\
"""


def _format_stance(stance: StanceHistoryEntry) -> str:
    if stance.kind == "position":
        subject = f"{stance.asset_description or 'unknown asset'} {stance.direction or ''}".strip()
    else:
        subject = f"{stance.sentiment or 'unstated'} on {stance.scope or stance.asset_description or 'the market'}"
    date_suffix = f" | {stance.stated_at.isoformat()}" if stance.stated_at else ""
    quotes = "; ".join(f'"{quote}"' for quote in stance.quotes)
    return f"- {stance.kind} | {subject} | {quotes}{date_suffix}"


def analyze_analyst(
    *,
    analyst_name: str,
    claims: list[ClaimHistoryEntry],
    stances: list[StanceHistoryEntry] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
) -> AnalystMetaAnalysis:
    """`system_prompt`/`model` override META_ANALYST_SYSTEM_PROMPT and the configured model for
    one call. See claim_finder.extract_claims for why that seam exists."""
    settings = get_settings()

    claims_text = "\n".join(
        f"- id={claim.claim_id} | {claim.asset_description} | "
        f"condition: {'; '.join(claim.condition_trigger) if claim.condition_trigger else 'none'} | "
        f"claim: {claim.claim} | horizon: {claim.horizon} | "
        f"status: {claim.status} | verdict: {claim.verdict or 'not yet graded'} | "
        f"rationale: {claim.rationale or 'n/a'}"
        for claim in claims
    )

    if stances:
        stances_text = "\n".join(_format_stance(stance) for stance in stances)
        stances_block = f"\n\nDisclosed positions/sentiment history:\n{stances_text}"
    else:
        stances_block = "\n\nNo disclosed positions/sentiment history is available for this analyst."

    user_content = f"Analyst: {analyst_name}\n\nClaim history:\n{claims_text}{stances_block}"

    return parse_structured(
        model=model or settings.meta_analyst_model,
        system=system_prompt or META_ANALYST_SYSTEM_PROMPT,
        user_content=user_content,
        schema=AnalystMetaAnalysis,
        max_tokens=16000,
        thinking=True,
    )
