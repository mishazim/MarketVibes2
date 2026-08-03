"""CSV history of every run, plus rolling-trend context for the synthesis step.

Mirrors the JobSearch/sheets.py pandas pattern. Each agent run appends one row.
The trailing trend (default 5 trading days) is what implements the "timing offset":
today's mood is judged relative to the recent baseline, not in isolation.
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import config

COLUMNS = [
    "timestamp_et", "date", "slot", "sentiment", "buy_score", "confidence",
    "vix", "vix_chg_pct", "sp500", "sp500_chg_pct", "nasdaq", "nasdaq_chg_pct",
    "dow_chg_pct", "tnx", "summary", "drivers",
]

# Numeric mapping for averaging sentiment over the window.
_SENTIMENT_SCORE = {"negative": -1, "neutral": 0, "positive": 1}

# Characters that trigger formula evaluation when a CSV is opened in a
# spreadsheet (Excel/Sheets/LibreOffice). The summary/drivers text is derived
# from model output influenced by untrusted web content, so neutralize it.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value) -> str:
    """Prefix a leading formula-trigger char with ' so spreadsheets treat the
    cell as text rather than a formula (CSV/formula-injection guard)."""
    text = "" if value is None else str(value)
    if text and text[0] in _FORMULA_TRIGGERS:
        return "'" + text
    return text


def load() -> pd.DataFrame:
    if not os.path.exists(config.HISTORY_CSV):
        df = pd.DataFrame(columns=COLUMNS)
        df.to_csv(config.HISTORY_CSV, index=False)
        return df
    return pd.read_csv(config.HISTORY_CSV, dtype=str).fillna("")


def append_run(brief: dict, snapshot: dict, slot: str) -> dict:
    """Build a row from the brief + market snapshot, append it, and return the row."""
    now = datetime.now(ZoneInfo(config.TIMEZONE))

    def lvl(key):
        return snapshot.get(key, {}).get("level", "")

    def chg(key):
        return snapshot.get(key, {}).get("chg_pct", "")

    row = {
        "timestamp_et": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "slot": slot,
        "sentiment": brief.get("sentiment", ""),
        "buy_score": brief.get("buy_score", ""),
        "confidence": brief.get("confidence", ""),
        "vix": lvl("vix"),
        "vix_chg_pct": chg("vix"),
        "sp500": lvl("sp500"),
        "sp500_chg_pct": chg("sp500"),
        "nasdaq": lvl("nasdaq"),
        "nasdaq_chg_pct": chg("nasdaq"),
        "dow_chg_pct": chg("dow"),
        "tnx": lvl("tnx"),
        "summary": _csv_safe(brief.get("summary", "")),
        "drivers": _csv_safe(json.dumps(brief.get("drivers", []), ensure_ascii=False)),
    }
    df = load()
    new = pd.DataFrame([{c: row.get(c, "") for c in COLUMNS}])
    # Avoid the empty-concat FutureWarning on the very first run.
    df = new if df.empty else pd.concat([df, new], ignore_index=True)
    df.to_csv(config.HISTORY_CSV, index=False)
    return row


def today_runs(date_str: str) -> list:
    """Return every row recorded for `date_str` (YYYY-MM-DD), oldest first.

    Used to build the intraday trajectory table in the end-of-day summary email.
    """
    df = load()
    if df.empty:
        return []
    day = df[df["date"] == date_str].copy()
    if day.empty:
        return []
    return day.sort_values("timestamp_et").to_dict("records")


def recent_trend(window_days: int = None) -> dict:
    """Summarize the last `window_days` distinct trading days for synthesis context.

    Returns a dict with a compact day-by-day table, an average sentiment score, the
    number of consecutive non-positive (negative/neutral) days, and the VIX trend.
    """
    window_days = window_days or config.TREND_WINDOW_DAYS
    df = load()
    if df.empty:
        return {"has_history": False, "summary": "No prior runs recorded yet."}

    recent_dates = sorted(df["date"].unique())[-window_days:]
    sub = df[df["date"].isin(recent_dates)].copy()

    # Daily aggregate: average of that day's runs.
    daily = []
    for d in recent_dates:
        day = sub[sub["date"] == d]
        scores = pd.to_numeric(day["buy_score"], errors="coerce").dropna()
        sent_vals = [_SENTIMENT_SCORE.get(s, 0) for s in day["sentiment"] if s]
        avg_sent = sum(sent_vals) / len(sent_vals) if sent_vals else 0
        label = "positive" if avg_sent > 0.33 else "negative" if avg_sent < -0.33 else "neutral"
        vix_vals = pd.to_numeric(day["vix"], errors="coerce").dropna()
        daily.append({
            "date": d,
            "sentiment": label,
            "avg_buy_score": round(scores.mean(), 1) if not scores.empty else None,
            "vix": round(vix_vals.iloc[-1], 1) if not vix_vals.empty else None,
        })

    # Consecutive non-positive streak counting back from the most recent day.
    streak = 0
    for day in reversed(daily):
        if day["sentiment"] in ("negative", "neutral"):
            streak += 1
        else:
            break

    vix_series = [d["vix"] for d in daily if d["vix"] is not None]
    vix_trend = "n/a"
    if len(vix_series) >= 2:
        vix_trend = "rising" if vix_series[-1] > vix_series[0] else \
                    "falling" if vix_series[-1] < vix_series[0] else "flat"

    table = "\n".join(
        f"  {d['date']}: {d['sentiment']:8s} | buy {d['avg_buy_score']} | VIX {d['vix']}"
        for d in daily
    )
    return {
        "has_history": True,
        "days": daily,
        "consecutive_nonpositive_days": streak,
        "vix_trend": vix_trend,
        "summary": (
            f"Last {len(daily)} trading day(s):\n{table}\n"
            f"Consecutive negative/neutral days (the 'rut'): {streak}. "
            f"VIX trend over window: {vix_trend}."
        ),
    }


if __name__ == "__main__":
    print(recent_trend()["summary"])
