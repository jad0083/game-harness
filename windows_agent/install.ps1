# Installs the game agent for the current Windows user.
#
# Remote bootstrap (files served by scripts/serve-agent.sh on the controller):
#   $env:GA_SRC='http://<controller-ip>:8000'; irm "$env:GA_SRC/install.ps1" | iex
# Local: run from a folder containing agent.py (and optionally agent_token.txt):
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# What it does:
#   1. Ensures Python 3 is available (installs it per-user via winget if not).
#   2. Copies agent.py + agent_token.txt to %LOCALAPPDATA%\GameAgent.
#   3. Adds an inbound firewall rule for TCP 8765 from the local subnet only (one UAC prompt).
#   4. Registers a logon task that runs the agent in your desktop session, then starts it.

$ErrorActionPreference = 'Stop'
$Port = if ($env:GA_PORT) { [int]$env:GA_PORT } else { 8765 }
$Dest = Join-Path $env:LOCALAPPDATA 'GameAgent'
$TaskName = 'GameAgent'
$RuleName = "Game Agent (TCP $Port)"

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

# --- 1. Python ---------------------------------------------------------------
Step 'Checking for Python 3'
function Find-Pythonw {
    # Native stderr must not become a terminating error here (PowerShell 5.1 + 'Stop').
    $ErrorActionPreference = 'Continue'
    $probe = 'import sys; print(sys.executable)'
    foreach ($cmd in @('py', 'python')) {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { continue }
        # Ask the real interpreter for its path; the Microsoft Store alias stub fails this.
        try {
            if ($cmd -eq 'py') { $out = & py -3 -c $probe 2>$null } else { $out = & python -c $probe 2>$null }
        } catch { continue }
        $path = @($out) | Where-Object { $_ } | Select-Object -Last 1
        if ($LASTEXITCODE -eq 0 -and $path -and (Test-Path $path)) {
            $w = Join-Path (Split-Path $path) 'pythonw.exe'
            if (Test-Path $w) { return $w }
        }
    }
    return $null
}
$Pythonw = Find-Pythonw
if (-not $Pythonw) {
    Step 'Python not found; installing Python 3.12 for this user via winget'
    winget install --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $Pythonw = Find-Pythonw
    if (-not $Pythonw) {
        $guess = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\pythonw.exe'
        if (Test-Path $guess) { $Pythonw = $guess } else { throw 'Python install failed; install Python 3 from python.org and re-run.' }
    }
}
Write-Host "    using $Pythonw"

# --- 2. Files ----------------------------------------------------------------
Step "Installing agent to $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
if ($env:GA_SRC) {
    Invoke-WebRequest "$env:GA_SRC/agent.py" -UseBasicParsing -OutFile (Join-Path $Dest 'agent.py')
    try {
        Invoke-WebRequest "$env:GA_SRC/agent_token.txt" -UseBasicParsing -OutFile (Join-Path $Dest 'agent_token.txt')
    } catch { Write-Host '    no token served; the agent will generate one' }
} else {
    $here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    Copy-Item (Join-Path $here 'agent.py') $Dest -Force
    $tok = Join-Path $here 'agent_token.txt'
    if (Test-Path $tok) { Copy-Item $tok $Dest -Force }
}

# --- 3. Firewall (needs admin once) --------------------------------------------
Step "Allowing inbound TCP $Port from the local subnet"
if (-not (Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue)) {
    $cmd = "New-NetFirewallRule -DisplayName '$RuleName' -Direction Inbound -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null"
    Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList '-NoProfile', '-Command', $cmd
    if (-not (Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue)) {
        throw 'Firewall rule was not created (UAC declined?). Re-run and accept the prompt.'
    }
} else { Write-Host '    rule already present' }

# --- 4. Logon task -----------------------------------------------------------
# Runs non-elevated in the interactive session: services cannot see or drive the desktop.
Step "Registering logon task '$TaskName'"
$action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Dest\agent.py`" --port $Port" -WorkingDirectory $Dest
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Step "Agent is running on port $Port"
} else {
    Write-Warning "Agent is not listening yet; check $Dest\agent.log"
}
Write-Host ''
Write-Host 'Tips: run the game in Borderless/Windowed mode (exclusive fullscreen can capture black),'
Write-Host '      and stay logged in with the screen unlocked while the agent plays.'
Write-Host "Uninstall: Unregister-ScheduledTask $TaskName; Remove-NetFirewallRule -DisplayName '$RuleName'; Remove-Item -Recurse '$Dest'"
