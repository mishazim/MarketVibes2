"""NYSE trading-calendar gate.

Determines whether the US stock market is open on a given date so the agent only
runs on trading days (skips weekends, holidays, and notes early-close half-days).

Run directly to sanity-check:  python market_calendar.py
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

import config

_NYSE = mcal.get_calendar("XNYS")


def _as_date(d) -> date:
    if d is None:
        return datetime.now(ZoneInfo(config.TIMEZONE)).date()
    if isinstance(d, datetime):
        return d.date()
    return d


def is_trading_day(d=None) -> bool:
    """True if the NYSE holds a regular or half session on the given date (default: today ET)."""
    d = _as_date(d)
    sched = _NYSE.schedule(start_date=d, end_date=d)
    return not sched.empty


def market_status(d=None) -> dict:
    """Return {open: bool, reason: str, early_close: bool, close_time: str|None}."""
    d = _as_date(d)
    sched = _NYSE.schedule(start_date=d, end_date=d)

    if sched.empty:
        if d.weekday() >= 5:
            reason = "weekend"
        else:
            reason = "market holiday"
        return {"open": False, "reason": reason, "early_close": False, "close_time": None}

    # Detect half-day (early close, typically 1:00 PM ET) by comparing to a normal 4 PM close.
    market_close = sched.iloc[0]["market_close"].tz_convert(config.TIMEZONE)
    early_close = market_close.hour < 16
    hour_12 = market_close.hour % 12 or 12
    ampm = "AM" if market_close.hour < 12 else "PM"
    close_str = f"{hour_12}:{market_close.minute:02d} {ampm} ET"
    return {
        "open": True,
        "reason": "early close (half day)" if early_close else "regular session",
        "early_close": early_close,
        "close_time": close_str,
    }


if __name__ == "__main__":
    samples = {
        "today": None,
        "a Saturday (2026-06-06)": date(2026, 6, 6),
        "New Year's Day (2026-01-01)": date(2026, 1, 1),
        "July 4 observed (2026-07-03)": date(2026, 7, 3),
        "day after Thanksgiving half-day (2025-11-28)": date(2025, 11, 28),
    }
    for label, d in samples.items():
        print(f"{label}: {market_status(d)}")
