# Setup

One-time setup, then the tool runs itself hourly (9 AM–6 PM ET) on trading days,
emails a 4 PM vibe check and a 6 PM daily summary, and runs a post-close heartbeat
check at 6:35 PM. Everything here is free — no paid API key required anywhere.

## 1. Install Ollama and pull the model

```powershell
winget install Ollama.Ollama
ollama pull qwen2.5:7b-instruct
```

Ollama installs as a background service, so it's already listening on
`http://localhost:11434` after install — `local_llm.py` talks to it directly, no
API key involved. Confirm with `ollama list`.

## 2. Install Python dependencies

```powershell
cd C:\Users\mzimm\Projects\MarketVibes2
pip install -r requirements.txt
```

## 3. Reddit API app (optional, for the social sentiment tier)

Reddit blocks anonymous scraping outright (403 regardless of User-Agent), so the
social tier authenticates via a free "script" app's OAuth2 client-credentials
grant:

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) (log in first).
2. Click **create app** / **create another app**. Name it anything, pick type
   **script**, and set the redirect URI to `http://localhost:8080` (required but
   unused).
3. Copy the **client ID** (the string under the app name) and the **secret** into
   `.env`:
   ```
   REDDIT_CLIENT_ID=...
   REDDIT_CLIENT_SECRET=...
   ```

If you skip this, `feeds.py` skips the social tier gracefully and the brief runs
on the legacy (MarketWatch/CNBC/Yahoo) + macro (Fed) tiers only.

## 4. Gmail (to receive the brief by email)

The tool sends mail with the Gmail API using a **send-scoped** OAuth token. This
project was forked from `MarketVibes`, so `credentials.json`/`token.json` were
copied over and should already work without re-authenticating — if `token.json`
is missing or expired:

1. In the [Google Cloud Console](https://console.cloud.google.com/): create/select a
   project → enable the **Gmail API** → create an **OAuth client ID** (Desktop app) →
   download it as `credentials.json` into this folder.
2. Run the one-time consent flow:
   ```powershell
   python gmail_auth.py
   ```
   A browser opens; approve the **Send email** permission. `token.json` is saved.

> Don't want email yet? Skip this and always pass `--dry-run`. The brief still prints
> to the console and saves to `output/` + `history.csv`.

## 5. Test the pipeline (no email, ignores market hours)

```powershell
python feeds.py                                    # confirm RSS/Reddit sources return headlines
python local_llm.py                                # confirm Ollama JSON round-trip works
python market_calendar.py                          # holiday/weekend gate sanity check
python market_data.py                              # live VIX/index snapshot
python brief.py --slot h13 --dry-run --force       # one hourly run, end-to-end
python brief.py --slot h16 --dry-run --force       # render the 4 PM vibe check
python brief.py --slot h18 --dry-run --force       # render the 6 PM daily summary
python notify.py                                   # fire a sample buy-alert toast
python heartbeat.py --force                        # run the post-close health check now
```

`--force` bypasses the market-open gate (so you can test on a weekend); `--dry-run`
skips the email. Hourly slots are `h09`..`h18`; the `h16` (4 PM) run emails a vibe
check and the `h18` (6 PM) run emails the daily summary (the intraday table is built
from whatever runs are already in `history.csv` for today).

Since a 7B local model is less nuanced than Claude Sonnet, spot-check a few runs'
`summary`/`buy_score` against the original project's saved briefs in
`../MarketVibes/output/` for rough calibration sanity before trusting it live.

## 6. Schedule the hourly runs

From an **elevated** PowerShell prompt:

```powershell
.\setup_tasks.ps1
```

This registers two tasks:

- `MarketVibes2_Hourly` — fires every hour from 9:00 AM to 6:00 PM on weekdays. Each
  run records a data point to `history.csv`; the 4:00 PM run emails a vibe check and
  the 6:00 PM run emails the daily summary with the intraday trajectory. The script's
  NYSE calendar gate skips holidays automatically and auto-detects the hourly slot.
- `MarketVibes2_Heartbeat` — fires once at 6:35 PM on weekdays and verifies the day's
  hourly runs all landed in `history.csv`, firing a desktop alert if any are missing.

Any run with a buy score of 4+ also fires a **desktop notification** (Windows Action
Center / macOS Notification Center). The task runs only while you're logged in, which
is required for toasts to appear; the daily email sends regardless.

> **Timezone:** the tool always reasons in US Eastern. If this PC is not on Eastern
> time, the trigger clock times fire at local time — set the PC to Eastern or edit the
> `-At` values in `setup_tasks.ps1` to your local equivalents.

Verify / manage:

```powershell
Get-ScheduledTask -TaskName 'MarketVibes2*'                                  # list
Start-ScheduledTask -TaskName 'MarketVibes2_Hourly'                          # run now
Get-ScheduledTask -TaskName 'MarketVibes2*' | Unregister-ScheduledTask -Confirm:$false  # remove
```

## Files at a glance

| File | Role |
|------|------|
| `brief.py` | Orchestrator / entry point |
| `config.py` | Tickers, feed sources, Ollama model, trend window |
| `market_calendar.py` | NYSE open/closed gate |
| `market_data.py` | VIX + index snapshot |
| `feeds.py` | Free RSS/Reddit scrape (data gathering) |
| `local_llm.py` | Ollama client — JSON-mode chat helper |
| `news_sentiment.py` | Classifies gathered headlines via the local model |
| `analysis.py` | Contrarian 1–5 synthesis via the local model |
| `history.py` | `history.csv` + trailing trend |
| `emailer.py` / `gmail_auth.py` | Email delivery |
| `notify.py` | Desktop buy-alert toast (score ≥ 4) |
| `heartbeat.py` | Post-close check that the day's runs landed |
| `setup_tasks.ps1` | Windows Task Scheduler registration |
| `output/` | Saved Markdown briefs |

## Falling back to the original (Claude-based) MarketVibes

If local output quality disappoints, the original project at `../MarketVibes` is
untouched and can be re-enabled independently — see its own `ops/PAUSED.md` for
how it was paused and how to resume it. The two projects are fully independent
(separate folders, separate `history.csv`, separate scheduled tasks), so both can
even run side by side if you want to compare them.
