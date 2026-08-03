"""Central configuration for MarketVibes 2.0 (Local)."""

import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)

# Load .env HERE, before any os.environ reads below. config is often imported
# (directly or via emailer) before an entrypoint calls load_dotenv(), so relying
# on the caller to load .env first left EMAIL_TO empty and silently broke the 6pm
# email. Use an explicit path so it works regardless of the process's cwd (the
# scheduled task does not run from the project dir).
load_dotenv(os.path.join(BASE_DIR, ".env"))

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
HISTORY_CSV = os.path.join(BASE_DIR, "history.csv")

# We always operate in US Eastern (NYSE) time per the project brief.
TIMEZONE = "America/New_York"

# Local inference via Ollama (no API key, no per-token cost). Both the news
# sweep's classification pass and the final synthesis use this one model.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")

# Reddit blocks anonymous scraping (403 on both the JSON and .rss endpoints,
# regardless of User-Agent), so the social tier authenticates via a free
# "script" app's OAuth2 client-credentials grant instead. Create one at
# reddit.com/prefs/apps and put the id/secret in .env — this is still $0 cost,
# just requires registration. Sources are skipped gracefully if unset.
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

# Hourly cadence. The script runs once an hour on the (Eastern) clock from
# RUN_START_HOUR through RUN_END_HOUR inclusive. Every run gathers data and
# records it to history; only the final (end-of-day) run emails — a single daily
# summary that recaps the day's intraday trajectory. Hour is local (Eastern) and
# used for slot auto-detection.
RUN_START_HOUR = 9    # first hourly run (9:00 AM ET)
RUN_END_HOUR = 18     # last run / end-of-day summary email (6:00 PM ET)


def _format_hour_label(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    h12 = hour % 12 or 12
    return f"{h12}:00 {suffix} ET"


# Slots are generated per hour, keyed "h09".."h18". The scheduled task auto-detects
# the slot from the current ET hour, so no slot argument is needed in normal use.
SLOTS = {
    f"h{h:02d}": {"hour": h, "label": _format_hour_label(h)}
    for h in range(RUN_START_HOUR, RUN_END_HOUR + 1)
}

# Two runs email each day: the 4 PM "vibe check" (a preliminary read that still
# leaves time to act) and the 6 PM "sentiment summary" (the final end-of-day call).
# Every other hourly run stays silent and just records its data point to history.
VIBE_CHECK_SLOT = "h16"
END_OF_DAY_SLOT = f"h{RUN_END_HOUR:02d}"

# Desktop notifications (notify.py) fire on any run whose buy_score is at or above
# this threshold — a "buy alert." 4 = "Good time to buy", 5 = "Excellent". The
# daily email always sends; notifications are the timely heads-up for buy signals.
BUY_ALERT_THRESHOLD = 4

# Tickers fetched as the objective anchor. yfinance symbols.
MARKET_TICKERS = {
    "vix": "^VIX",      # CBOE Volatility Index — the "fear index"
    "sp500": "^GSPC",   # S&P 500
    "nasdaq": "^IXIC",  # Nasdaq Composite
    "dow": "^DJI",      # Dow Jones Industrial Average
    "tnx": "^TNX",      # 10-year Treasury yield
}

# Rolling window (trading days) that defines the "trend" / timing offset.
TREND_WINDOW_DAYS = 5

# Cap on headlines pulled per individual feed, so the local model's prompt stays
# small and fast (a 7B model is far more sensitive to context bloat than Sonnet).
MAX_HEADLINES_PER_FEED = 10

# Free data sources for feeds.py, grouped into the same three tiers the
# synthesis prompt already reasons about. RSS feeds are fetched with
# `feedparser`; Reddit is fetched via its OAuth2 API (see REDDIT_CLIENT_ID
# above) using `oauth.reddit.com`. Each source is fetched independently and
# failures are swallowed so one dead feed never kills a run — verify these
# periodically, since RSS URLs and API behavior do drift.
FEED_SOURCES = {
    "social": [
        ("Reddit r/wallstreetbets", "wallstreetbets"),
        ("Reddit r/stocks", "stocks"),
        ("Reddit r/investing", "investing"),
    ],
    "legacy": [
        ("MarketWatch Top Stories", "https://www.marketwatch.com/rss/topstories"),
        ("CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ],
    "macro": [
        ("Federal Reserve Press Releases", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ],
}

# Short tier descriptions handed to the classification prompt, so the local model
# knows what each tier is meant to represent (mirrors the old SOURCE_TIERS text).
SOURCE_TIERS = {
    "social": (
        "Social media retail sentiment (Reddit r/wallstreetbets, r/stocks, "
        "r/investing). Fast but noisy."
    ),
    "legacy": (
        "Legacy and financial press (MarketWatch, CNBC, Yahoo Finance). "
        "Authoritative macro signals."
    ),
    "macro": (
        "Macro and geopolitical uncertainty drivers, primarily Federal Reserve "
        "policy announcements."
    ),
}

# Delivery
EMAIL_TO = os.environ.get("BRIEF_EMAIL_TO", "")  # set in .env; required for email
EMAIL_FROM = os.environ.get("BRIEF_EMAIL_FROM", "me")  # "me" = authenticated Gmail user

DISCLAIMER = (
    "This brief is an automated, contrarian decision-support tool — not financial "
    "advice. Sentiment can be wrong and markets are unpredictable. Do your own "
    "research before investing."
)
