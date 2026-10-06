# MarketVibes 2.0 (Local)

> **$0-cost, contrarian stock-market sentiment consultant.** Reads the macro mood from free RSS/Reddit sources every hour through the trading day, anchors it against real price action (VIX + index moves), and distills it into a single 1–5 buy signal via a locally-run LLM — no paid API calls anywhere in the pipeline. Two emails land each trading day: a 4 PM vibe check and a 6 PM close summary.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Powered by Ollama](https://img.shields.io/badge/Powered%20by-Ollama-000000.svg)](https://ollama.com/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](https://learn.microsoft.com/windows/)
[![Status: active](https://img.shields.io/badge/Status-active-brightgreen.svg)](#)

This is a fork of [MarketVibes](../MarketVibes) that replaces every paid Anthropic
API call (the web-search news sweep and the synthesis) with **free equivalents**:
RSS/Reddit scraping for data (`feeds.py`) and a local Ollama model
(`qwen2.5:7b-instruct`) for both classification and the contrarian synthesis
(`local_llm.py`). **The original Claude-based MarketVibes is kept intact as a
fallback** — see its own README if local output quality ever disappoints and you
want to fall back to it.

A contrarian stock-market **consultant** (not an autobuying bot). Every hour of the
trading day it reads the macro mood from open-source intelligence — Reddit,
legacy/financial press, and macro/geopolitical news — anchors that read against real
market price action (VIX + index moves), and boils it down to:

- **One sentiment label:** positive / negative / neutral
- **One buy score (1–5):** how good a time it is for a long-term retail investor to buy in

## The thesis (contrarian)

> "Stonks must go up" — usually. But during war, disasters, poor economic conditions,
> Fed tightening, or disruptive-tech shake-ups, the market goes *on sale*.

- Sustained **negative/neutral** mood + **fear** (high/rising VIX, indices down) = stocks on sale → **high buy score (4–5)**.
- A **bounce** back to positive after a rut (VIX falling, indices rallying) = expensive → **low buy score (1–2)**.
- The score judges the **trend relative to a trailing baseline** (the "timing offset"), not today in isolation.

| Score | Meaning |
|-------|---------|
| 5 | Excellent time to buy — multi-day fear streak + elevated VIX (deep sale / capitulation) |
| 4 | Good time to buy — negativity building, VIX rising |
| 3 | Neutral — no clear contrarian edge |
| 2 | Getting expensive — sentiment recovering, VIX falling |
| 1 | Bad time to buy — market rallying out of a rut, euphoric, low VIX |

## Daily schedule (US Eastern, market-open days only)

- **Hourly, 9:00 AM – 6:00 PM** — each run sweeps the news, scores the mood, and
  records a data point to `history.csv`.
- **4:00 PM** — sends a **vibe check** email: a preliminary read that still leaves
  time to act before the close.
- **6:00 PM** — sends the **daily summary** email: the final 1–5 call plus an
  intraday table of how sentiment, the buy score, and VIX moved through the day.
- **6:35 PM** — a **heartbeat** check confirms the day's hourly runs all landed in
  `history.csv` and fires a desktop alert if any are missing (`heartbeat.py`).

Weekends and NYSE holidays are skipped automatically (`market_calendar.py`).

## How it works

```
brief.py  →  market_calendar (open gate)
          →  market_data      (VIX/S&P/Nasdaq/Dow/10yr anchor, yfinance + stooq fallback)
          →  feeds            (free RSS/Reddit scrape, 3 source tiers — no paid API)
          →  news_sentiment   (local Ollama model classifies the gathered headlines)
          →  history          (trailing trend = the "timing offset")
          →  analysis         (local Ollama model → contrarian synthesis → 1–5 buy score)
          →  output/*.md + history.csv  (every hourly run)
          →  notify           (every run: desktop toast IF buy_score ≥ 4 — a "buy alert")
          →  email                       (4 PM vibe check + 6 PM daily summary + intraday table)

heartbeat.py  →  6:35 PM: verify the day's hourly runs all reached history.csv, alert if not
```

`local_llm.py` talks to Ollama's local HTTP API (`http://localhost:11434` by
default) — no API key, no network egress, no per-token cost.

## Quick start

See **SETUP.md**. TL;DR:

```powershell
winget install Ollama.Ollama
ollama pull qwen2.5:7b-instruct
pip install -r requirements.txt
# optional but recommended: register a free Reddit "script" app at
# reddit.com/prefs/apps and put its id/secret in .env (REDDIT_CLIENT_ID/SECRET) —
# without it the social tier is skipped and the brief runs on legacy+macro only.
python brief.py --slot h18 --dry-run --force      # test the daily summary, no email
.\setup_tasks.ps1                                  # register the hourly + heartbeat tasks (elevated)
```

## Notes & limitations

- **$0 marginal cost.** No Anthropic (or any paid) API is called anywhere in this
  fork — data comes from free RSS feeds + the Reddit API's free tier, and inference
  runs entirely on your own GPU via Ollama.
- **Quality tradeoff vs. the Claude version.** A 7B local model is less nuanced at
  the nuanced contrarian calibration than Sonnet. Spot-check a few daily briefs
  against the original `MarketVibes/output/` history; if quality disappoints, the
  original Claude-based project is kept running as a fallback.
- **Reddit requires a free app registration.** Reddit blocks anonymous scraping
  outright (403 regardless of User-Agent), so the social tier authenticates via
  OAuth2 client-credentials using a free "script" app (see Quick start). Without
  credentials it's skipped gracefully — legacy + macro feeds still run.
- **Buy-alert notifications need an interactive login.** A desktop toast fires on
  any run with a buy score of 4+ (Windows Action Center / macOS Notification Center,
  no extra dependency). Toasts only appear while you're logged in, so the scheduled
  task runs "only when user is logged on." The daily email always sends regardless.
- **Market data can be flaky.** yfinance occasionally rate-limits; the tool falls back
  to stooq and, failing that, runs on sentiment alone with confidence capped.
- **RSS/API endpoints can drift.** `feeds.py` degrades any single dead source to an
  empty list rather than failing the run — re-run `python feeds.py` standalone
  periodically to confirm all sources are still live.
- **A daily heartbeat guards against silent failures.** After the close (6:35 PM) a
  separate `MarketVibes2_Heartbeat` task checks that the day's hourly runs all reached
  `history.csv`; if any are missing it fires a desktop alert.
- **Going back to sleep after a run depends on the Windows lock screen.** The hourly and
  heartbeat tasks wake the PC but do not sleep it again themselves. That is done by a
  separate `SleepAfterWakeTasks` task from the ProjectRecall project
  (`scripts\sleep_after_wake.ps1` there), which sleeps the PC once the run has finished and
  the PC is still on the lock screen. **Fail-safe: keep "require sign-in on wake" turned on**
  (Settings > Accounts > Sign-in options). With it off there is no lock screen, any stray
  key press or mouse bump after a wake counts as someone at the desk, and the PC stays on
  until it is put to sleep by hand. Decisions are logged to
  `%LOCALAPPDATA%\ProjectRecall\sleep_after_wake.log`.
- **Task Scheduler wakes the PC from sleep, but not from shutdown.** Each hourly run
  has its own `-WakeToRun` trigger, so the machine wakes itself for every slot even
  from sleep (wake timers must be enabled in Windows power settings). A full shutdown
  still skips runs; for always-on reliability, a cloud scheduler is a future upgrade.
- **Not financial advice.** Decision support only; every brief carries a disclaimer.
