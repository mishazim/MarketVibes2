"""News OSINT sweep over free, no-auth data sources (see feeds.py).

Pulls current market-moving headlines across three source tiers (social,
legacy/financial press, macro/geopolitical) and asks the local model to
classify and synthesize them into a structured read of themes and raw
sentiment. Replaces the old Claude web_search sweep — the data-gathering step
(feeds.py) and the classification step (local_llm.py) are now separate.
"""

import config
import feeds
import local_llm

SWEEP_PROMPT = """You are a market-sentiment analyst doing an open-source intelligence read for a US retail investor. The current run is the **{slot_label}** check on {today}. We operate on US Eastern time and care about the US stock market (S&P 500 / Nasdaq).

Below are today's headlines, already gathered from three source tiers:

## Tier 1 — {social}
{social_headlines}

## Tier 2 — {legacy}
{legacy_headlines}

## Tier 3 — {macro}
{macro_headlines}

Focus on the kinds of uncertainty that move markets: war/conflict, natural disasters, Federal Reserve / interest-rate / inflation news, elections and policy, major upcoming IPOs, disruptive-technology shifts, earnings surprises, and broad risk-on / risk-off mood.

Read across all three tiers above, then return ONLY a JSON object with these exact keys:

- "headlines": array of up to 8 objects, each {{ "title": str, "source": str, "tier": "social"|"legacy"|"macro", "sentiment": "positive"|"negative"|"neutral", "note": str }} — pick the most market-relevant of the headlines above.
- "dominant_themes": array of 2-5 short strings naming the day's big storylines
- "uncertainty_drivers": array of strings — active sources of fear/uncertainty (empty if calm)
- "raw_sentiment": one of "positive" | "negative" | "neutral" — your unweighted read of the overall mood from the news alone
- "sentiment_rationale": 1-2 sentences explaining the raw_sentiment read

Return ONLY the JSON object, no other text. If a tier has no headlines, reason from the tiers that do. If all tiers are empty, still return the object with best-effort empty arrays."""


def _fmt_tier_headlines(headlines: list) -> str:
    if not headlines:
        return "(no headlines gathered for this tier)"
    return "\n".join(f"- [{h['source']}] {h['title']}" for h in headlines)


def gather_findings(slot: str, today: str) -> dict:
    """Gather free-source headlines and classify them via the local model."""
    print("  Gathering headlines from RSS/Reddit sources...")
    all_headlines = feeds.gather_all_headlines()
    prompt = SWEEP_PROMPT.format(
        slot_label=config.SLOTS[slot]["label"],
        today=today,
        social=config.SOURCE_TIERS["social"],
        legacy=config.SOURCE_TIERS["legacy"],
        macro=config.SOURCE_TIERS["macro"],
        social_headlines=_fmt_tier_headlines(all_headlines.get("social", [])),
        legacy_headlines=_fmt_tier_headlines(all_headlines.get("legacy", [])),
        macro_headlines=_fmt_tier_headlines(all_headlines.get("macro", [])),
    )
    print("  Classifying via local model (may take up to a minute)...")
    result = local_llm.chat_json(prompt, max_tokens=1500)
    if result is None:
        print("    Warning: local model returned no parseable findings; returning empty.")
        return _empty_findings()
    return result


def _empty_findings() -> dict:
    return {
        "headlines": [], "dominant_themes": [], "uncertainty_drivers": [],
        "raw_sentiment": "neutral",
        "sentiment_rationale": "News sweep returned no parseable data.",
    }
