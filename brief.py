"""MarketVibes 2.0 (Local) — main entry point.

Runs one hourly slot of the daily cycle: gates on the NYSE calendar, pulls
objective market data, sweeps free RSS/Reddit sources for news, synthesizes a
contrarian 1-5 buy-signal brief via a local Ollama model, records it to
history, and saves a Markdown copy. Runs hourly 9 AM-6 PM ET; only the final
(6 PM) run emails — one daily summary recapping the day's intraday trajectory.

Usage:
    python brief.py                      # auto-detect slot from current ET hour
    python brief.py --slot h13           # force a specific hourly slot (h09..h18)
    python brief.py --slot h18 --dry-run # render the daily summary without emailing
    python brief.py --force              # bypass the market-open gate (testing)
"""

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Windows consoles default to cp1252, which can't encode the emoji used in briefs.
# Reconfigure stdout/stderr to UTF-8 so printing never crashes the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from dotenv import load_dotenv

import config
import history
import notify
from analysis import synthesize_brief
from emailer import render_daily_summary, render_markdown, render_vibe_check, send_brief
from market_calendar import market_status
from market_data import get_market_snapshot
from news_sentiment import gather_findings

load_dotenv()


def detect_slot(now: datetime) -> str:
    """Pick the slot whose scheduled hour is closest to the current ET hour."""
    hour = now.hour
    return min(config.SLOTS, key=lambda s: abs(config.SLOTS[s]["hour"] - hour))


def main():
    parser = argparse.ArgumentParser(description="Generate a market sentiment brief")
    parser.add_argument("--slot", choices=list(config.SLOTS), default=None,
                        help="Which daily run (default: auto-detect from ET hour)")
    parser.add_argument("--dry-run", action="store_true", help="Skip sending the email")
    parser.add_argument("--force", action="store_true",
                        help="Bypass the market-open gate (for testing)")
    args = parser.parse_args()

    now = datetime.now(ZoneInfo(config.TIMEZONE))
    today = now.strftime("%Y-%m-%d")
    slot = args.slot or detect_slot(now)

    print(f"=== MarketVibes Brief — {today} | slot: {slot} ({config.SLOTS[slot]['label']}) ===")

    # 1. Market-open gate.
    status = market_status(now)
    if not status["open"] and not args.force:
        print(f"Market is closed today ({status['reason']}). Skipping run.")
        return
    if status["open"] and status["early_close"]:
        print(f"Note: today is a half-day ({status['close_time']} close).")

    # 2. Objective market anchor.
    print("Fetching market data...")
    snapshot = get_market_snapshot()
    if not snapshot.get("available"):
        print("  Market data unavailable — proceeding on sentiment only (confidence capped).")

    # 3. News sweep + 4. synthesis.
    findings = gather_findings(slot, today)
    trend = history.recent_trend()
    brief = synthesize_brief(findings, snapshot, trend, slot, today)

    # 5. Persist (history first so trend reflects this run for downstream tooling).
    history.append_run(brief, snapshot, slot)
    markdown = render_markdown(brief, snapshot, trend, slot, today)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(config.OUTPUT_DIR, f"brief_{today}_{slot}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print("\n" + markdown)
    print(f"Saved: {out_path}")

    # 5b. Timely buy alert: fire a desktop notification on every run whose score
    #     clears the threshold (independent of the once-daily summary email).
    notify.notify_if_buy(brief)

    # 6. Deliver — two runs email each day: the 4 PM "vibe check" (a preliminary
    #    read that still leaves time to act) and the 6 PM "sentiment summary" (the
    #    final end-of-day call). Every other hourly run stays silent: it just
    #    records its data point to history.csv.
    #
    #    Gate on an EXACT ET-hour match, not just the detected slot. detect_slot()
    #    snaps to the nearest slot, so a late or after-hours catch-up run (e.g. Task
    #    Scheduler firing at 7 PM via StartWhenAvailable) auto-detects to h18 and
    #    would otherwise re-send the 6 PM summary. Requiring now.hour == the slot's
    #    scheduled hour means such out-of-band runs only record to history.
    is_email_slot = slot in (config.VIBE_CHECK_SLOT, config.END_OF_DAY_SLOT)
    in_slot_hour = now.hour == config.SLOTS[slot]["hour"]
    if not (is_email_slot and in_slot_hour):
        vibe_label = config.SLOTS[config.VIBE_CHECK_SLOT]["label"]
        eod_label = config.SLOTS[config.END_OF_DAY_SLOT]["label"]
        if is_email_slot and not in_slot_hour:
            print(f"(off-hour run at {now.hour:02d}:00 ET detected as {slot}; "
                  f"recording to history only — no duplicate email)")
        else:
            print(f"(hourly run recorded; emails go out at the {vibe_label} vibe check "
                  f"and the {eod_label} sentiment summary)")
        return

    intraday = history.today_runs(today)
    is_summary = slot == config.END_OF_DAY_SLOT
    if is_summary:
        email_md = render_daily_summary(brief, snapshot, trend, today, intraday)
        kind, label = "Sentiment Summary", "sentiment summary"
    else:
        email_md = render_vibe_check(brief, snapshot, trend, today, intraday)
        kind, label = "Vibe Check", "vibe check"

    print(f"\n--- {label} email ---\n" + email_md)
    if args.dry_run:
        print(f"(dry-run: {label} email skipped)")
    else:
        try:
            send_brief(brief, email_md, kind=kind)
        except Exception as e:
            print(f"  Email failed ({e}). The {label} is still saved at {out_path}.")


if __name__ == "__main__":
    main()
