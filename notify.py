"""Cross-platform desktop notifications for buy alerts.

A notification fires only when a brief is a *buy alert* — a buy_score at or above
config.BUY_ALERT_THRESHOLD. It lands in the OS's native notification center with no
third-party dependency:

  - macOS:   `osascript` "display notification" (Notification Center)
  - Windows: a WinRT toast shown via PowerShell (Action Center)
  - Linux:   `notify-send` if available (best-effort)

A notification only shows when an interactive desktop session is present, so this is
meant for the hourly runs while the user is logged in. Any failure is swallowed with
a printed warning — a missing notification must never break the brief run.
"""

import os
import platform
import shutil
import subprocess

import config

# When the scheduled task runs under the windowless interpreter (pythonw), any
# console child it spawns gets its own fresh console window unless we suppress it.
# CREATE_NO_WINDOW keeps the toast's PowerShell fully hidden. No-op off Windows.
_NO_WINDOW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if platform.system() == "Windows" else {}
)

_SCORE_BLURB = {
    4: "Good time to buy",
    5: "Excellent time to buy",
}


def is_buy_alert(brief: dict) -> bool:
    """True if the brief's buy_score meets the alert threshold."""
    try:
        score = int(brief.get("buy_score", 0))
    except (TypeError, ValueError):
        return False
    return score >= config.BUY_ALERT_THRESHOLD


def notify_if_buy(brief: dict) -> bool:
    """Send a desktop notification iff the brief is a buy alert.

    Returns True if a notification was dispatched, False otherwise.
    """
    if not is_buy_alert(brief):
        return False

    score = brief.get("buy_score", "?")
    sentiment = (brief.get("sentiment") or "").upper()
    blurb = _SCORE_BLURB.get(score, "Buy signal")
    title = f"MarketVibes — Buy {score}/5: {blurb}"

    summary = (brief.get("summary") or "").strip()
    # Notifications are short — use the first line/sentence, capped.
    body = summary.split("\n")[0][:200] if summary else f"{sentiment} sentiment — possible buying opportunity."

    ok = _send(title, body)
    if ok:
        print(f"  Buy alert: desktop notification sent (buy {score}/5).")
    return ok


def send(title: str, body: str) -> bool:
    """Fire a desktop notification with an arbitrary title/body.

    Public entry point for callers other than the buy-alert path (e.g. the daily
    heartbeat check). Returns True if the notification was dispatched.
    """
    return _send(title, body)


def _send(title: str, body: str) -> bool:
    system = platform.system()
    try:
        if system == "Darwin":
            return _send_macos(title, body)
        if system == "Windows":
            return _send_windows(title, body)
        return _send_linux(title, body)
    except Exception as e:  # never let a notification problem break the run
        print(f"  Notification failed ({e}).")
        return False


def _send_macos(title: str, body: str) -> bool:
    """Notification Center via AppleScript. Zero dependencies (osascript is built in)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = (
        f'display notification "{esc(body)}" '
        f'with title "{esc(title)}" sound name "Glass"'
    )
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    return True


# PowerShell that shows a WinRT toast. Title/body are passed via environment
# variables (MV_TITLE/MV_BODY) so no quoting or injection issues arise. An
# AppUserModelID is registered under HKCU (no admin) so the toast is attributed
# to "MarketVibes" instead of a generic host process.
_WINDOWS_TOAST_PS = r"""
$ErrorActionPreference = 'Stop'
$AppId = 'MarketVibes'

$root = 'HKCU:\Software\Classes\AppUserModelId\' + $AppId
if (-not (Test-Path $root)) { New-Item -Path $root -Force | Out-Null }
New-ItemProperty -Path $root -Name 'DisplayName' -Value 'MarketVibes' -PropertyType String -Force | Out-Null

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $template.GetElementsByTagName('text')
[void]$texts.Item(0).AppendChild($template.CreateTextNode($env:MV_TITLE))
[void]$texts.Item(1).AppendChild($template.CreateTextNode($env:MV_BODY))

$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId)
$notifier.Show($toast)
"""


def _send_windows(title: str, body: str) -> bool:
    """Action Center toast via PowerShell + WinRT. No pip dependency."""
    env = {**os.environ, "MV_TITLE": title, "MV_BODY": body}
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
         "-Command", _WINDOWS_TOAST_PS],
        check=True, capture_output=True, env=env, **_NO_WINDOW,
    )
    return True


def _send_linux(title: str, body: str) -> bool:
    """Best-effort Linux support via notify-send, if it's installed."""
    if not shutil.which("notify-send"):
        print("  Notification skipped (notify-send not found).")
        return False
    subprocess.run(["notify-send", title, body], check=True, capture_output=True)
    return True


if __name__ == "__main__":
    # Manual smoke test: fire a sample buy alert on whatever OS this is.
    sample = {
        "buy_score": 5,
        "sentiment": "negative",
        "summary": "Multi-day fear streak with a spiking VIX — the market looks on sale.",
    }
    print("buy alert?", is_buy_alert(sample))
    notify_if_buy(sample)
