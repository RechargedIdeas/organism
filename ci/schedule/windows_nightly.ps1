<#
.SYNOPSIS
Registers or removes a daily Task Scheduler job that runs the Organism nightly CI tier.

.DESCRIPTION
The job runs "python ci/run.py run --tier nightly" from the repository root using the project's
.venv interpreter. Results land in ci/runs/ like any other run. Nothing is registered unless
this script is run without -Remove.

.PARAMETER At
Daily start time, HH:mm. Default 02:00.

.PARAMETER Remove
Unregister the job instead of creating it.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File ci\schedule\windows_nightly.ps1 -At 02:00

.EXAMPLE
powershell -ExecutionPolicy Bypass -File ci\schedule\windows_nightly.ps1 -Remove
#>
[CmdletBinding()]
param(
    [string]$At = "02:00",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$TaskName = "OrganismNightlyCI"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task $TaskName"
    } else {
        Write-Host "Scheduled task $TaskName is not registered"
    }
    return
}

if (-not (Test-Path $Python)) {
    throw "No project interpreter at $Python. Create .venv first (see ci/README.md)."
}

$action = New-ScheduledTaskAction -Execute $Python -Argument "ci\run.py run --tier nightly" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Organism nightly CI tier (ci/run.py)" `
    -Force | Out-Null

Write-Host "Registered $TaskName to run daily at $At from $Root"
Write-Host "Results: $(Join-Path $Root 'ci\runs\latest.json')"
