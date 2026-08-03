<#
.SYNOPSIS
    Registers two Windows Scheduled Tasks for MarketVibes 2.0 (Local):
    MarketVibes2_Hourly runs the brief once an hour from 9:00 AM through 6:00 PM
    on weekdays (each run records a data point to history.csv; the 4:00 PM run
    emails a vibe check and the 6:00 PM run emails the daily summary recapping
    the day's intraday trajectory), and MarketVibes2_Heartbeat runs a post-close
    health check at 6:35 PM. The script itself skips market holidays via the
    NYSE calendar gate in market_calendar.py and auto-detects the hourly slot.
    This project has its own task names (MarketVibes2_*) so it can run
    side-by-side with the original MarketVibes tasks without colliding.

.NOTES
    Run from an ELEVATED PowerShell prompt:
        .\setup_tasks.ps1

    The brief always operates on US Eastern time. If this PC's timezone is NOT
    US Eastern, the trigger clock times below will fire at the wrong moment —
    set the PC to Eastern, or adjust the -At time to your local equivalent.
#>

$ErrorActionPreference = "Stop"

# Resolve project dir and the Python interpreter.
$ProjectDir = $PSScriptRoot
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $Python) { throw "Could not find python on PATH. Install Python or edit `$Python in this script." }

# Run the scheduled task through the WINDOWLESS interpreter (pythonw.exe / pyw.exe)
# so no console window flashes up each hour and interrupts whatever you're doing.
# It lives next to the normal interpreter; fall back (with a warning) if it isn't there.
$pyDir  = Split-Path $Python -Parent
$pyLeaf = Split-Path $Python -Leaf
$wLeaf  = $pyLeaf -replace 'python\.exe$', 'pythonw.exe' -replace '^py\.exe$', 'pyw.exe'
$Pythonw = Join-Path $pyDir $wLeaf
if (-not (Test-Path $Pythonw)) {
    Write-Warning "Windowless interpreter '$wLeaf' not found next to $Python. The task will use $pyLeaf and a console window may flash each run."
    $Pythonw = $Python
}

Write-Host "Project:  $ProjectDir"
Write-Host "Python:   $Python"
Write-Host "Pythonw:  $Pythonw  (used by the tasks - windowless)"

# Warn if the machine isn't on Eastern time.
$tz = (Get-TimeZone).Id
if ($tz -notmatch "Eastern") {
    Write-Warning "This PC's timezone is '$tz', not US Eastern. The trigger times will fire at LOCAL time, which may not match market hours. Consider switching to Eastern or adjusting the -At value."
}

$TaskName = "MarketVibes2_Hourly"

# brief.py auto-detects the slot from the current ET hour, so no --slot argument.
$action = New-ScheduledTaskAction -Execute $Pythonw `
    -Argument "brief.py" -WorkingDirectory $ProjectDir

# Weekdays, one DISCRETE trigger per hour 9 AM..6 PM (NOT a single repeating
# trigger). This is deliberate and load-bearing: WakeToRun only registers an RTC
# wake timer for a trigger's START time, NOT for the occurrences of a repetition.
# With the old "9 AM + repeat hourly" trigger the PC woke for the 9 AM run only;
# once it slept mid-morning, the 10 AM-6 PM runs were silently skipped until
# something woke the machine by hand (observed 2026-06-24: slept 10:31 AM, h11-h14
# missed, manual wake 3:27 PM). Giving every hour its own trigger means every hour
# gets its own wake timer, so the PC wakes itself for all 10 runs even from sleep.
# The script's NYSE gate still handles holidays.
$trigger = 9..18 | ForEach-Object {
    New-ScheduledTaskTrigger -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At ([datetime]::Today.AddHours($_))
}

# WakeToRun + battery flags so runs survive sleep and unplugged operation on a
# laptop (the PC wakes itself for each slot). Toasts still require a logged-in
# session. Wake timers must be allowed in Windows power settings for this to work.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "MarketVibes 2.0 (Local) hourly brief (9 AM-6 PM ET; emails a vibe check at 4 PM and the daily summary at 6 PM)" `
    -Force | Out-Null

Write-Host "Registered: $TaskName (weekdays, hourly 9:00 AM-6:00 PM)"

# --- Daily heartbeat -------------------------------------------------------
# A second task runs heartbeat.py once after the close (6:35 PM, just after the
# 6:00 PM run) to verify the day's hourly runs actually landed in history.csv.
# If any expected run is missing it fires a desktop notification; on a market
# holiday it exits quietly. This is the safety net for silent hourly failures.
$HeartbeatTask = "MarketVibes2_Heartbeat"

$hbAction = New-ScheduledTaskAction -Execute $Pythonw `
    -Argument "heartbeat.py" -WorkingDirectory $ProjectDir

$hbTrigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 6:35PM

$hbSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $HeartbeatTask -Action $hbAction -Trigger $hbTrigger `
    -Settings $hbSettings -Description "MarketVibes 2.0 (Local) daily heartbeat - alerts if the day's hourly runs are missing from history.csv" `
    -Force | Out-Null

Write-Host "Registered: $HeartbeatTask (weekdays, 6:35 PM)"

Write-Host "`nDone. Verify with:  Get-ScheduledTask -TaskName 'MarketVibes2*'"
Write-Host "Remove with:        Get-ScheduledTask -TaskName 'MarketVibes2*' | Unregister-ScheduledTask -Confirm:`$false"
