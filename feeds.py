"""Free data sources for the news sweep — replaces Claude's web_search.

Pulls RSS feeds and Reddit across the same three source tiers (social/legacy/
macro) the synthesis prompt already reasons about. Every fetch degrades
gracefully to an empty list on failure (dead feed, network hiccup, missing
credentials) so one bad source never kills a run — mirrors the stooq-fallback
pattern in market_data.py.

Reddit blocks anonymous scraping outright (403 on both the JSON and .rss
endpoints, regardless of User-Agent), so the social tier authenticates via a
free "script" app's OAuth2 client-credentials grant instead — still $0 cost,
just requires the one-time app registration documented in config.py.
"""

import time

import feedparser
import requests

import config

# Reddit (and some RSS hosts) reject generic/blank User-Agents outright.
USER_AGENT = "MarketVibes2/1.0 (personal contrarian market brief; local, non-commercial)"

_reddit_token = {"value": None, "expires_at": 0.0}


def _fetch_rss(name: str, url: str) -> list[dict]:
    try:
        parsed = feedparser.parse(url, agent=USER_AGENT)
        if parsed.bozo and not parsed.entries:
            raise parsed.bozo_exception or RuntimeError("feed parse failed")
        entries = parsed.entries[:config.MAX_HEADLINES_PER_FEED]
        return [
            {"title": e.get("title", "").strip(), "source": name, "url": e.get("link", "")}
            for e in entries if e.get("title")
        ]
    except Exception as exc:
        print(f"    Warning: RSS fetch failed for {name} ({exc}); skipping.")
        return []


def _get_reddit_token() -> str | None:
    """Fetch (and cache) an app-only OAuth2 token via the client-credentials grant.

    This grant needs only the app's id/secret (no Reddit username/password) and
    is meant exactly for reading public, non-user-specific content like this.
    """
    if not (config.REDDIT_CLIENT_ID and config.REDDIT_CLIENT_SECRET):
        return None
    if _reddit_token["value"] and time.time() < _reddit_token["expires_at"]:
        return _reddit_token["value"]
    try:
        resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        _reddit_token["value"] = payload["access_token"]
        _reddit_token["expires_at"] = time.time() + payload.get("expires_in", 3600) - 60
        return _reddit_token["value"]
    except Exception as exc:
        print(f"    Warning: Reddit OAuth token fetch failed ({exc}); skipping Reddit sources.")
        return None


def _fetch_reddit(name: str, subreddit: str) -> list[dict]:
    token = _get_reddit_token()
    if not token:
        return []
    try:
        resp = requests.get(
            f"https://oauth.reddit.com/r/{subreddit}/top",
            params={"limit": config.MAX_HEADLINES_PER_FEED, "t": "day"},
            headers={"User-Agent": USER_AGENT, "Authorization": f"bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        children = resp.json().get("data", {}).get("children", [])
        return [
            {
                "title": c["data"].get("title", "").strip(),
                "source": name,
                "url": "https://reddit.com" + c["data"].get("permalink", ""),
            }
            for c in children if c.get("data", {}).get("title")
        ]
    except Exception as exc:
        print(f"    Warning: Reddit fetch failed for {name} ({exc}); skipping.")
        return []


_TIER_FETCHERS = {"social": _fetch_reddit}


def gather_all_headlines() -> dict:
    """Fetch every configured source, tagged by tier.

    Returns {tier: [ {title, source, url}, ... ]} — dead/unreachable sources
    just contribute an empty list rather than failing the whole sweep.
    """
    result = {}
    for tier, sources in config.FEED_SOURCES.items():
        fetcher = _TIER_FETCHERS.get(tier, _fetch_rss)
        tier_headlines = []
        for name, url in sources:
            tier_headlines.extend(fetcher(name, url))
        result[tier] = tier_headlines
    return result


if __name__ == "__main__":
    findings = gather_all_headlines()
    for tier, headlines in findings.items():
        print(f"\n=== {tier} ({len(headlines)} headlines) ===")
        for h in headlines[:5]:
            print(f"  - [{h['source']}] {h['title']}")
