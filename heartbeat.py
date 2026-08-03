"""Daily heartbeat — verify the scheduled hourly runs actually produced data.

The hourly MarketVibes_Hourly task can fail silently (bad API key, network
outage, rate-limit exhaustion, a crash) and the only visible symptom would be a
missing 6 PM email and a stale history.csv. This check runs once after the
close, looks at history.csv for today's expected hourly rows, and fires a
desktop notification (and appends a line to heartbeat.log) if any are missing.

On a market holiday no runs are expected, so it exits quietly. Run manually with
`python heartbeat.py` to check now, or `python heartbeat.py --force` to bypass
the market-open gate while testing.
"""

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Match brief.py: Windows consoles default to cp1252 and choke on any emoji.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import config
import history
import notify
from market_calendar import market_status

LOG_PATH = os.path.join(config.BASE_DIR, "heartbeat.log")


def _log(message: str) -> None:
    """Append a timestamped line to heartbeat.log and echo it to stdout."""
    stamp = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"  (could not write heartbeat.log: {e})")


def expected_slots(now: datetime) -> list:
    """Slots whose scheduled hour has already passed at `now` (ET)."""
    return [s for s, meta in config.SLOTS.items() if meta["hour"] <= now.hour]


def check(now: datetime = None, force: bool = False) -> bool:
    """Return True if today's runs look healthy, False if an alert was raised."""
    now = now or datetime.now(ZoneInfo(config.TIMEZONE))
    today = now.strftime("%Y-%m-%d")

    status = market_status(now)
    if not status["open"] and not force:
        _log(f"{today}: market closed ({status['reason']}) — no runs expected. OK.")
        return True

    expected = expected_slots(now)
    seen = {r.get("slot") for r in history.today_runs(today)}
    missing = [s for s in expected if s not in seen]

    if not missing:
        _log(f"{today}: OK — all {len(expected)} expected run(s) present "
             f"({', '.join(expected)}).")
        return True

    # Something didn't run. Fire a desktop alert and record it.
    if not seen:
        body = (f"No briefs recorded today ({today}). The hourly task is likely "
                f"failing — check Task Scheduler and run.log.")
    else:
        body = (f"{len(missing)} of {len(expected)} runs missing today "
                f"({today}): {', '.join(missing)}. Check the hourly task.")
    _log(f"{today}: ALERT — missing {missing} (have {sorted(seen) or 'nothing'}).")
    notify.send("MarketVibes heartbeat: runs MISSING", body)
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Daily heartbeat check for MarketVibes scheduled runs")
    parser.add_argument("--force", action="store_true",
                        help="Check even on a market-closed day (for testing)")
    args = parser.parse_args()
    healthy = check(force=args.force)
    sys.exit(0 if healthy else 1)


if __name__ == "__main__":
    main()
