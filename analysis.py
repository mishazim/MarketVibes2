"""Final synthesis: combine the news findings, the objective market snapshot, and
the trailing trend into one brief with a contrarian 1-5 buy score.

This module holds the scoring rubric. Market data is passed as ground truth so the
model anchors on real price action rather than hallucinating it.
"""

import config
import local_llm
from market_data import format_snapshot

SYNTHESIS_PROMPT = """You are a contrarian market consultant for a US retail investor. Your job is NOT to predict prices but to judge whether the market looks like it is "on sale" — a good time for a long-term retail investor to buy in.

## Core thesis (contrarian)
- Sustained NEGATIVE or NEUTRAL sentiment plus FEAR in the market (elevated/rising VIX, indices down) = stocks on sale = GOOD time to buy.
- A bounce back to POSITIVE sentiment after a rut (VIX falling, indices rallying) = getting expensive = BAD time to buy.
- The signal is about the TREND relative to the recent baseline, not just today in isolation.

## Today's news read ({slot_label}, {today})
Raw news sentiment: {raw_sentiment}
Rationale: {sentiment_rationale}
Dominant themes: {themes}
Uncertainty drivers: {drivers}
Headlines:
{headlines}

## Objective market data (ground truth — do not contradict)
{market_block}

## Recent trend (the timing offset / baseline)
{trend_block}

## Your task
Weigh the news sentiment AGAINST the market data and the recent trend. If the news read and the price action diverge, lower your confidence. Then output ONLY a JSON object:

- "sentiment": "positive" | "negative" | "neutral"  — overall mood for today's market
- "buy_score": integer 1-5 using this contrarian rubric:
    5 = Excellent time to buy (high conviction): multi-day negative/fearful streak AND elevated/spiking VIX, indices down — deep sale / possible capitulation.
    4 = Good time to buy: negative sentiment building, VIX rising, no bounce yet.
    3 = Neutral: mixed / range-bound, no clear contrarian edge.
    2 = Getting expensive: sentiment recovering toward positive, VIX falling.
    1 = Bad time to buy (expensive): market rallying out of a rut — positive/euphoric mood, low VIX.
- "confidence": "low" | "medium" | "high" — based on agreement between sentiment and market data, and how clean the multi-day trend is.
- "summary": 3-5 sentence plain-English brief a busy investor can read in 20 seconds. Lead with the call.
- "drivers": array of 2-4 short strings — the specific factors driving today's score.
- "caveats": 1-2 sentences on what could make this read wrong.

Return ONLY the JSON object, no other text."""


def _fmt_headlines(headlines: list) -> str:
    if not headlines:
        return "  (none parsed)"
    lines = []
    for h in headlines[:8]:
        lines.append(
            f"  - [{h.get('tier','?')}/{h.get('sentiment','?')}] "
            f"{h.get('title','')} ({h.get('source','')})"
        )
    return "\n".join(lines)


def synthesize_brief(findings: dict, snapshot: dict, trend: dict, slot: str,
                     today: str) -> dict:
    prompt = SYNTHESIS_PROMPT.format(
        slot_label=config.SLOTS[slot]["label"],
        today=today,
        raw_sentiment=findings.get("raw_sentiment", "neutral"),
        sentiment_rationale=findings.get("sentiment_rationale", ""),
        themes=", ".join(findings.get("dominant_themes", [])) or "none",
        drivers=", ".join(findings.get("uncertainty_drivers", [])) or "none",
        headlines=_fmt_headlines(findings.get("headlines", [])),
        market_block=format_snapshot(snapshot),
        trend_block=trend.get("summary", "No prior history."),
    )
    print("  Synthesizing brief...")
    brief = local_llm.chat_json(prompt, max_tokens=1500)
    if brief is None:
        return _fallback_brief("Synthesis returned no parseable JSON.")

    # Validate / clamp.
    brief["sentiment"] = brief.get("sentiment", "neutral")
    try:
        brief["buy_score"] = max(1, min(5, int(brief.get("buy_score", 3))))
    except (TypeError, ValueError):
        brief["buy_score"] = 3
    if not snapshot.get("available") and brief.get("confidence") == "high":
        brief["confidence"] = "medium"  # no market anchor → cap confidence
    return brief


def _fallback_brief(reason: str) -> dict:
    return {
        "sentiment": "neutral",
        "buy_score": 3,
        "confidence": "low",
        "summary": f"Could not generate a full brief ({reason}). Defaulting to neutral.",
        "drivers": [reason],
        "caveats": "Automated fallback — treat as no signal.",
    }
