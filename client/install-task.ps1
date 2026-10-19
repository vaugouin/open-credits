# Installs (or reinstalls) the scheduled task that runs the open-credits worker all the time.
#
# The task starts at logon, as the current user and only while that user is logged on (the mapped drives
# holding the films, T: and U:, exist only in the user's session), with no window, at below-normal
# priority, and restarts the worker 5 minutes after a crash. The worker sends each bundle once ready,
# queues the movies added to Plex (every 10 minutes, ahead of the rest) and, when the queue is empty,
# the back catalogue. Its output goes to %LOCALAPPDATA%\opencredits\worker.log.
#
# Run it again after updating the client: it syncs the virtual environment and restarts the task.
#   powershell -ExecutionPolicy Bypass -File C:\Users\vaugo\Code\open-credits\client\install-task.ps1
#   powershell -ExecutionPolicy Bypass -File ...\install-task.ps1 -Remove

param([switch]$Remove)

$TaskName = "open-credits worker"
$Client = $PSScriptRoot

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "removed the task '$TaskName'"
}
if ($Remove) { return }

# the virtual environment the task runs, brought to the checked-out version
uv sync --project $Client
if (-not $?) { throw "uv sync failed" }
$Pythonw = Join-Path $Client ".venv\Scripts\pythonw.exe"

$Action = New-ScheduledTaskAction -Execute $Pythonw -WorkingDirectory $Client `
    -Argument "-m opencredits.cli worker --send --watch-plex --back-catalogue"
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -Priority 7 -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings `
    -Description "open-credits: reads film credits from the Plex library and sends them to the server (client\install-task.ps1)" | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output "task '$TaskName' installed and started; log: $env:LOCALAPPDATA\opencredits\worker.log"
