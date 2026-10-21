"""Plain-text renderings of a claim and a resolution: what DeepEval's judge reads."""

from __future__ import annotations


def _bullets(items: list[str]) -> str:
    return "\n".join(f"  - {i}" for i in items)


def claim_text(c: dict) -> str:
    lines = [
        f"Asset: {c['asset_description']} (tickers: {', '.join(c.get('suggested_ticker') or []) or 'none'})",
        f"Claim: {c['claim']}",
        f"Horizon: {c['horizon']}",
        "Conditions (only if): " + ("; ".join(c["condition_trigger"]) if c.get("condition_trigger") else "none"),
        f"Stated implication: {c.get('stated_implication') or 'none'}",
        "Grounds:\n" + _bullets(c["grounds"]),
        "Warrant:\n" + _bullets(c["warrant"]),
        "Backing:\n" + (_bullets(c["backing"]) if c.get("backing") else "  none"),
        "Invalidation:\n" + (_bullets(c["rebuttal_invalidation"]) if c.get("rebuttal_invalidation") else "  none"),
        f"Qualifier: {c.get('qualifier') or 'none'}; confidence: {c.get('confidence')}",
    ]
    return "\n".join(lines)


def source_text(video: dict) -> str:
    return f"Title: {video['title']}\nPublished: {video['published_at']}\n\nTRANSCRIPT:\n{video['transcript']}"


def resolution_text(r: dict) -> str:
    b = r.get("benchmark")
    bench = (
        f"{b['benchmark_ticker']} returned {b['benchmark_return_pct']}%; claim asset returned "
        f"{b['claim_return_pct']}%; beat benchmark: {b['beat_benchmark']}"
        if b
        else "none"
    )
    return (
        f"Outcome: {r['outcome']}\nVerdict: {r['verdict']}\nTrigger status: {r['trigger_status']}\n"
        f"Benchmark: {bench}\nRationale: {r['rationale']}"
    )


def analyzer_input_text(c: dict, published_at: str | None, as_of: str) -> str:
    return (
        f"Asset: {c['asset_description']}\n"
        f"Condition/trigger: {'; '.join(c['condition_trigger']) if c.get('condition_trigger') else 'none (unconditional)'}\n"
        f"Claim: {c['claim']}\nHorizon: {c['horizon']}\nSource published: {published_at}\nToday (as_of): {as_of}"
    )
