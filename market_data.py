"""Objective market-price anchor.

Fetches the VIX (fear index), S&P 500, Nasdaq, Dow, and 10-year Treasury yield —
current level plus 1-day % change — to ground the AI sentiment read against real
price action. yfinance is primary; stooq is a fallback for the indices.

Run directly to sanity-check:  python market_data.py
"""

from __future__ import annotations

import config


def _pct_change(prev: float, last: float) -> float | None:
    if prev in (None, 0) or last is None:
        return None
    return round((last - prev) / prev * 100, 2)


def _fetch_yfinance() -> dict:
    import yfinance as yf

    symbols = list(config.MARKET_TICKERS.values())
    # 5 calendar days covers a long weekend so we always get >=2 sessions.
    # threads=False avoids the sqlite "database is locked" error on yfinance's
    # shared timezone cache when several tickers download at once.
    data = yf.download(
        symbols, period="5d", interval="1d",
        auto_adjust=False, progress=False, group_by="ticker", threads=False,
    )

    snapshot = {}
    for key, sym in config.MARKET_TICKERS.items():
        try:
            closes = data[sym]["Close"].dropna()
        except (KeyError, TypeError):
            closes = None
        if closes is None or len(closes) == 0:
            snapshot[key] = {"level": None, "chg_pct": None}
            continue
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        snapshot[key] = {"level": round(last, 2), "chg_pct": _pct_change(prev, last)}
    return snapshot


def _fetch_stooq() -> dict:
    """Fallback for the equity indices via stooq (no VIX/TNX coverage there)."""
    import pandas as pd

    stooq_map = {"sp500": "^spx", "nasdaq": "^ndq", "dow": "^dji"}
    snapshot = {}
    for key, sym in stooq_map.items():
        try:
            url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
            df = pd.read_csv(url).dropna()
            last = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else None
            snapshot[key] = {"level": round(last, 2), "chg_pct": _pct_change(prev, last)}
        except Exception:
            snapshot[key] = {"level": None, "chg_pct": None}
    return snapshot


def get_market_snapshot() -> dict:
    """Return per-ticker {level, chg_pct} plus an 'available' flag.

    Never raises — on total failure returns a snapshot of Nones with available=False
    so the pipeline can still run on sentiment alone (with lowered confidence).
    """
    snapshot = {"available": False}
    try:
        snapshot.update(_fetch_yfinance())
    except Exception as e:
        print(f"  yfinance fetch failed ({e}); trying stooq fallback...")

    # Fill any missing index values from stooq.
    missing = [k for k in ("sp500", "nasdaq", "dow")
               if snapshot.get(k, {}).get("level") is None]
    if missing:
        try:
            fallback = _fetch_stooq()
            for k in missing:
                if fallback.get(k, {}).get("level") is not None:
                    snapshot[k] = fallback[k]
        except Exception as e:
            print(f"  stooq fallback failed ({e}).")

    # Available if we got at least the VIX or the S&P 500.
    snapshot["available"] = any(
        snapshot.get(k, {}).get("level") is not None for k in ("vix", "sp500")
    )
    return snapshot


def format_snapshot(snapshot: dict) -> str:
    """Human-readable one-block summary used in prompts and the brief."""
    if not snapshot.get("available"):
        return "Market data unavailable for this run."
    names = {
        "vix": "VIX (fear index)", "sp500": "S&P 500", "nasdaq": "Nasdaq",
        "dow": "Dow Jones", "tnx": "10-yr Treasury yield",
    }
    lines = []
    for key, name in names.items():
        d = snapshot.get(key, {})
        level, chg = d.get("level"), d.get("chg_pct")
        if level is None:
            continue
        chg_str = "n/a" if chg is None else f"{chg:+.2f}%"
        lines.append(f"- {name}: {level} ({chg_str} 1-day)")
    return "\n".join(lines)


if __name__ == "__main__":
    snap = get_market_snapshot()
    print(format_snapshot(snap))
    print(f"\navailable={snap['available']}")
