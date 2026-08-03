# Next steps

## Reddit OAuth app registration — BLOCKED 2026-08-03, needs retry

The social-sentiment tier (`feeds.py` → Reddit) needs a free "script" app's
client ID/secret in `.env` (`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`). Until
these are set, `feeds.py` skips the social tier gracefully and the brief runs
on legacy (MarketWatch/CNBC/Yahoo) + macro (Fed) only — this is a real but
narrower signal, not a broken pipeline.

**What happened:** at reddit.com/prefs/apps, the create-app form's "I'm not a
robot" reCAPTCHA got stuck in an infinite challenge loop — never resolved even
after signing into Chrome and trying to disable extensions. Likely just a
transient Google/Reddit-side bot-detection issue, not a problem with the form
itself (the form was filled in correctly: name `MarketVibes2`, type `script`,
redirect uri `http://localhost:8080`).

**To retry:**
1. Go to reddit.com/prefs/apps, fill in the same fields (name/script/redirect
   uri as above), and try the reCAPTCHA again — possibly on a different day,
   different network (no VPN), or a fully clean browser profile.
2. Once it succeeds, copy the client ID (string under the app name) and the
   secret into `MarketVibes2/.env`:
   ```
   REDDIT_CLIENT_ID=...
   REDDIT_CLIENT_SECRET=...
   ```
3. Verify with `python feeds.py` — the `social` tier should show >0 headlines
   from r/wallstreetbets, r/stocks, r/investing instead of 0.

Full registration steps are also in `SETUP.md` step 3.
