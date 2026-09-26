# Installs or updates the game agent (native game-agent.exe) for the current Windows user.
#
# Remote bootstrap (files served by scripts/serve-agent.sh on the controller):
#   $env:GA_SRC='http://<controller-ip>:8000'; irm "$env:GA_SRC/install.ps1" | iex
# Local: run from a folder containing game-agent.exe (and optionally agent_token.txt):
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# What it does:
#   1. Stops any running agent (a running exe is locked and cannot be overwritten).
#   2. Copies game-agent.exe + agent_token.txt to %LOCALAPPDATA%\GameAgent and writes roots.json
#      (game folders the agent may read: Stellaris/GalCiv4 documents and install dirs; and the only
#      files it may write: the governor's Stellaris mod and dlc_load.json, which enables mods).
#   3. Adds an inbound firewall rule for TCP 8765 from the local subnet only (one UAC prompt, first run only).
#   4. Registers a logon task that runs the agent in your desktop session, starts it, and checks /health.

$ErrorActionPreference = 'Stop'
$Port = if ($env:GA_PORT) { [int]$env:GA_PORT } else { 8765 }
$Dest = Join-Path $env:LOCALAPPDATA 'GameAgent'
$Exe = Join-Path $Dest 'game-agent.exe'
$TokenFile = Join-Path $Dest 'agent_token.txt'
$TaskName = 'GameAgent'
$RuleName = "Game Agent (TCP $Port)"

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

# --- 1. Stop the running agent ------------------------------------------------
Step 'Stopping any running agent'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}
Get-Process -Name 'game-agent' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$deadline = (Get-Date).AddSeconds(10)
while ((Get-Process -Name 'game-agent' -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 250
}
if (Get-Process -Name 'game-agent' -ErrorAction SilentlyContinue) {
    throw 'game-agent.exe is still running and cannot be replaced. Close it and re-run.'
}

# --- 2. Files & binary --------------------------------------------------------
Step "Installing agent to $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$tmpExe = "$Exe.new"
if ($env:GA_SRC) {
    Invoke-WebRequest "$env:GA_SRC/game-agent.exe" -UseBasicParsing -OutFile $tmpExe
    Move-Item -Force $tmpExe $Exe
    Write-Host "    downloaded game-agent.exe ($([math]::Round((Get-Item $Exe).Length / 1KB)) KB)"
    try {
        Invoke-WebRequest "$env:GA_SRC/agent_token.txt" -UseBasicParsing -OutFile $TokenFile
    } catch { Write-Host '    no token served; the agent will generate one' }
} else {
    $here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    $localExe = Join-Path $here 'game-agent.exe'
    if (-not (Test-Path $localExe)) {
        throw "game-agent.exe not found in $here. Build it with: cargo build --target x86_64-pc-windows-gnu --release --bin game-agent"
    }
    Copy-Item $localExe $Exe -Force
    Write-Host '    copied game-agent.exe'
    $tok = Join-Path $here 'agent_token.txt'
    if (Test-Path $tok) { Copy-Item $tok $TokenFile -Force }
}

# --- 2b. Read-only file roots (game saves, logs, game data) ----------------------
# The agent serves files only from these folders, read-only (GET /files/*).
Step 'Detecting game folders for read-only access'
# Documents may be redirected (e.g. to OneDrive) and a synced copy from another PC may sit next
# to the live one, so check the usual places and pick the folder the game wrote to most recently.
$docsDirs = @([Environment]::GetFolderPath('MyDocuments'), (Join-Path $env:USERPROFILE 'Documents'))
if ($env:OneDrive) { $docsDirs += $env:OneDrive; $docsDirs += Join-Path $env:OneDrive 'Documents' }
$docsDirs = @($docsDirs | Where-Object { $_ } | Select-Object -Unique)
function Get-LastWrite($dir) {
    $f = Get-ChildItem $dir -File -Recurse -Depth 1 -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($f) { $f.LastWriteTime } else { [datetime]::MinValue }
}
function Find-DocsFolder($rel) {
    $found = @(foreach ($d in $docsDirs) { $p = Join-Path $d $rel; if (Test-Path $p) { $p } })
    if ($found.Count -gt 1) {
        foreach ($p in $found) { Write-Host "    candidate $p (last write $(Get-LastWrite $p))" }
    }
    if ($found.Count -gt 0) {
        return ($found | Sort-Object { Get-LastWrite $_ } -Descending | Select-Object -First 1)
    }
    # Not created yet (a game creates it on first launch): keep the likely path; /files/roots
    # reports exists=false until then.
    return (Join-Path $docsDirs[0] $rel)
}
$steamLibs = @()
try {
    $steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction Stop).SteamPath
    $steamLibs += $steam
    $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
    if (Test-Path $vdf) {
        $steamLibs += Get-Content $vdf | Select-String '"path"\s+"(.+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\', '\' }
    }
} catch { Write-Host '    Steam not found in the registry' }
function Find-SteamGame($folder) {
    foreach ($lib in $steamLibs) {
        $p = Join-Path $lib "steamapps\common\$folder"
        if (Test-Path $p) { return (Resolve-Path $p).Path }
    }
    return $null
}
$candidates = [ordered]@{
    stellaris_docs    = Find-DocsFolder 'Paradox Interactive\Stellaris'
    stellaris_install = Find-SteamGame 'Stellaris'
    galciv4_docs      = Find-DocsFolder 'My Games\GalCiv4'
    galciv4_install   = Find-SteamGame 'Galactic Civilizations IV'
}
$roots = [ordered]@{}
foreach ($k in $candidates.Keys) {
    $v = $candidates[$k]
    if (-not $v) { continue }
    $roots[$k] = $v
    $note = if (Test-Path $v) { '' } else { '  (not created yet)' }
    Write-Host "    $k = $v$note"
}
# Writable: only the governor's Stellaris mod and the file that enables mods (dlc_load.json).
$writeRoots = [ordered]@{}
if ($roots['stellaris_docs']) {
    $writeRoots['stellaris_mods'] = [ordered]@{
        path  = $roots['stellaris_docs']
        allow = @('mod/governor_bridge/', 'mod/governor_bridge.mod', 'dlc_load.json')
    }
    Write-Host "    writable: $($roots['stellaris_docs']) (mod/governor_bridge/, mod/governor_bridge.mod, dlc_load.json)"
}
# No BOM: Windows PowerShell 5.1's Set-Content -Encoding UTF8 would add one.
[IO.File]::WriteAllText((Join-Path $Dest 'roots.json'), (@{ roots = $roots; write_roots = $writeRoots } | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding $false))

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
$action = New-ScheduledTaskAction -Execute $Exe -Argument "--port $Port" -WorkingDirectory $Dest
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
} catch {
    # An existing task created elevated can't be replaced from a normal shell ("Access is
    # denied"). It already runs the same exe path, so starting it is enough for an update.
    if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) { throw }
    Write-Host "    could not re-register ($($_.Exception.Message.Trim())); starting the existing task"
}
Start-ScheduledTask -TaskName $TaskName

# --- 5. Verify ----------------------------------------------------------------
Step 'Checking /health'
$health = $null
$deadline = (Get-Date).AddSeconds(10)
while (-not $health -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    try {
        $headers = @{}
        if (Test-Path $TokenFile) { $headers['Authorization'] = "Bearer $((Get-Content $TokenFile -Raw).Trim())" }
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -Headers $headers -TimeoutSec 2
    } catch { $health = $null }
}
if ($health) {
    Step "Agent v$($health.version) is running on port $Port; screen $($health.screen[0])x$($health.screen[1])"
} else {
    Write-Warning "Agent is not answering on port $Port. Run it by hand to see its output:  & '$Exe' --port $Port"
}
Write-Host ''
Write-Host 'Tips: run the game in Borderless/Windowed mode (exclusive fullscreen can capture black),'
Write-Host '      and stay logged in with the screen unlocked while the agent plays.'
Write-Host "Uninstall: Unregister-ScheduledTask $TaskName; Remove-NetFirewallRule -DisplayName '$RuleName'; Remove-Item -Recurse '$Dest'"
