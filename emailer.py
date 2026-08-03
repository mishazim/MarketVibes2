"""Render the brief to Markdown + HTML and email it via the Gmail API."""

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config
from market_data import format_snapshot

_SCORE_LABEL = {
    1: "1/5 — Bad time to buy (expensive)",
    2: "2/5 — Getting expensive",
    3: "3/5 — Neutral, no clear edge",
    4: "4/5 — Good time to buy",
    5: "5/5 — Excellent time to buy",
}
_EMOJI = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}


def render_markdown(brief: dict, snapshot: dict, trend: dict, slot: str, today: str) -> str:
    score = brief.get("buy_score", 3)
    sentiment = brief.get("sentiment", "neutral")
    drivers = "\n".join(f"- {d}" for d in brief.get("drivers", [])) or "- (none)"
    return f"""# MarketVibes Brief — {today}
**{config.SLOTS[slot]['label']}**

## Call: {_SCORE_LABEL.get(score, score)}
**Today's sentiment:** {_EMOJI.get(sentiment,'')} {sentiment.upper()}  |  **Confidence:** {brief.get('confidence','?')}

{brief.get('summary','')}

### What's driving today's score
{drivers}

### Market data (objective anchor)
{format_snapshot(snapshot)}

### Recent trend
{trend.get('summary','No prior history.')}

### Caveats
{brief.get('caveats','')}

---
_{config.DISCLAIMER}_
"""


def _intraday_table(rows: list) -> str:
    """Markdown for how the call moved across the day's hourly runs.

    `rows` are history dicts (see history.today_runs). Falls back to a note if the
    end-of-day run is the only data point recorded today.
    """
    if not rows:
        return "_(no intraday data points recorded today)_"
    lines = ["| Time (ET) | Sentiment | Buy | VIX |", "|---|---|---|---|"]
    for r in rows:
        # timestamp_et is "YYYY-MM-DD HH:MM:SS" — show HH:MM.
        ts = str(r.get("timestamp_et", ""))
        clock = ts[11:16] if len(ts) >= 16 else ts
        sentiment = (r.get("sentiment") or "?")
        emoji = _EMOJI.get(sentiment, "")
        buy = r.get("buy_score") or "?"
        vix = r.get("vix") or "?"
        lines.append(f"| {clock} | {emoji} {sentiment} | {buy}/5 | {vix} |")
    return "\n".join(lines)


def render_vibe_check(brief: dict, snapshot: dict, trend: dict, today: str,
                      intraday_rows: list) -> str:
    """4 PM "vibe check": a preliminary read of the day with the trajectory so far,
    framed as a not-yet-final call that still leaves time to act before the 6 PM
    sentiment summary."""
    score = brief.get("buy_score", 3)
    sentiment = brief.get("sentiment", "neutral")
    drivers = "\n".join(f"- {d}" for d in brief.get("drivers", [])) or "- (none)"
    eod_label = config.SLOTS[config.END_OF_DAY_SLOT]["label"]
    return f"""# MarketVibes Vibe Check — {today}

## Preliminary call: {_SCORE_LABEL.get(score, score)}
**Current sentiment:** {_EMOJI.get(sentiment,'')} {sentiment.upper()}  |  **Confidence:** {brief.get('confidence','?')}

_Preliminary read — the final sentiment summary follows at {eod_label}. This earlier check leaves you time to act on the day's vibe if you want to._

{brief.get('summary','')}

### Today's trajectory so far
{_intraday_table(intraday_rows)}

### What's driving the current score
{drivers}

### Market data (objective anchor)
{format_snapshot(snapshot)}

### Recent trend
{trend.get('summary','No prior history.')}

### Caveats
{brief.get('caveats','')}

---
_{config.DISCLAIMER}_
"""


def render_daily_summary(brief: dict, snapshot: dict, trend: dict, today: str,
                         intraday_rows: list) -> str:
    """End-of-day sentiment summary: the final call as the headline, plus an
    intraday trajectory table showing how the day's hourly runs moved."""
    score = brief.get("buy_score", 3)
    sentiment = brief.get("sentiment", "neutral")
    drivers = "\n".join(f"- {d}" for d in brief.get("drivers", [])) or "- (none)"
    return f"""# MarketVibes Sentiment Summary — {today}

## Call: {_SCORE_LABEL.get(score, score)}
**Final sentiment:** {_EMOJI.get(sentiment,'')} {sentiment.upper()}  |  **Confidence:** {brief.get('confidence','?')}

{brief.get('summary','')}

### Intraday trajectory (today's hourly runs)
{_intraday_table(intraday_rows)}

### What's driving the final score
{drivers}

### Market data (objective anchor)
{format_snapshot(snapshot)}

### Recent trend
{trend.get('summary','No prior history.')}

### Caveats
{brief.get('caveats','')}

---
_{config.DISCLAIMER}_
"""


def _markdown_to_html(md: str) -> str:
    """Minimal MD→HTML (headings, bold, list items) — no external dependency.

    Text content is HTML-escaped before any transform so model- and web-derived
    text can't inject markup (links, tags, etc.) into the email body.
    """
    import html
    import re

    def _is_table_sep(s):  # the "|---|---|" divider row under a table header
        return s.startswith("|") and set(s) <= set("|-: ")

    html_lines = []
    in_table = False
    for line in md.splitlines():
        s = line.rstrip()
        # Pipe-delimited table rows → <table>. The separator row opens the body.
        if s.startswith("|") and s.endswith("|"):
            if _is_table_sep(s):
                continue
            if not in_table:
                html_lines.append("<table style='border-collapse:collapse' border='1' cellpadding='4'>")
                in_table = True
            cells = [c.strip() for c in s.strip("|").split("|")]
            html_lines.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            html_lines.append("</table>")
            in_table = False
        if s.startswith("### "):
            html_lines.append(f"<h3>{html.escape(s[4:])}</h3>")
        elif s.startswith("## "):
            html_lines.append(f"<h2>{html.escape(s[3:])}</h2>")
        elif s.startswith("# "):
            html_lines.append(f"<h1>{html.escape(s[2:])}</h1>")
        elif s.startswith("- "):
            html_lines.append(f"<li>{html.escape(s[2:])}</li>")
        elif s == "---":
            html_lines.append("<hr>")
        elif s == "":
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p>{html.escape(s)}</p>")
    if in_table:
        html_lines.append("</table>")
    body = "\n".join(html_lines)
    # Bold (**...**) and italics (_..._). Applied after escaping; * and _ are
    # untouched by html.escape, so these markers still match and the only HTML
    # introduced is the <strong>/<em> tags themselves.
    body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body)
    body = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", body)
    return f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:640px'>{body}</div>"


def send_brief(brief: dict, markdown: str, kind: str = "Brief") -> None:
    from gmail_auth import get_gmail_service

    score = brief.get("buy_score", 3)
    sentiment = brief.get("sentiment", "neutral")
    subject = f"{_EMOJI.get(sentiment,'')} MarketVibes — {kind} {score}/5 ({sentiment})"

    msg = MIMEMultipart("alternative")
    msg["To"] = config.EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(markdown, "plain", "utf-8"))
    msg.attach(MIMEText(_markdown_to_html(markdown), "html", "utf-8"))

    if not config.EMAIL_TO:
        raise RuntimeError("BRIEF_EMAIL_TO is not set in .env — cannot send email.")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service = get_gmail_service()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"  Emailed brief to {config.EMAIL_TO}")
