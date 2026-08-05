# Verify OJ trading paths: Jarvis API, ngrok tunnel, webhook, live session.
# Intended schedule: 9:00 / 12:00 / 14:00 ET on weekdays.
param(
    [switch]$Fix,
    [switch]$Quiet
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path $PSScriptRoot -Parent
$StateDir = Join-Path $env:USERPROFILE '.openjarvis'
$LogFile = Join-Path $StateDir 'trading-path-verify.log'
$ResultFile = Join-Path $StateDir 'trading-path-verify.json'
$TunnelFile = Join-Path $StateDir 'tradingview-tunnel-url.txt'
$TradingToml = Join-Path $StateDir 'trading.toml'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { $Python = 'python' }

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function Write-Log([string]$Message) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    if (-not $Quiet) { Write-Host $line }
}

function Get-TomlString([string]$Key) {
    if (-not (Test-Path $TradingToml)) { return '' }
    $pattern = "^\s*$Key\s*=\s*""([^""]*)""\s*$"
    $m = Select-String -Path $TradingToml -Pattern $pattern | Select-Object -First 1
    if ($m) { return $m.Matches.Groups[1].Value.Trim() }
    return ''
}

function Test-Http([string]$Url, [int]$TimeoutSec = 12) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return @{ ok = ($r.StatusCode -eq 200); detail = "HTTP $($r.StatusCode)" }
    } catch {
        return @{ ok = $false; detail = $_.Exception.Message }
    }
}

function Test-Webhook([string]$Url) {
    $body = '{"strategy":"oj_0dte","event":"path_verify","symbol":"SPY","action":"suggest","price":1}'
    try {
        $headers = @{ 'Content-Type' = 'application/json'; 'ngrok-skip-browser-warning' = '1' }
        $r = Invoke-WebRequest -Uri $Url -Method POST -Body $body -Headers $headers -UseBasicParsing -TimeoutSec 20
        $ok = ($r.StatusCode -eq 200)
        $snippet = if ($r.Content.Length -gt 160) { $r.Content.Substring(0, 160) } else { $r.Content }
        return @{ ok = $ok; detail = "HTTP $($r.StatusCode) $snippet" }
    } catch {
        return @{ ok = $false; detail = $_.Exception.Message }
    }
}

function Get-NgrokPublicBase {
    try {
        $t = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 5
        if ($t.tunnels -and $t.tunnels.Count -gt 0) {
            return [string]$t.tunnels[0].public_url
        }
    } catch {}
    if (Test-Path $TunnelFile) {
        $m = Select-String -Path $TunnelFile -Pattern '^public_base=(.+)$' | Select-Object -First 1
        if ($m) { return $m.Matches.Groups[1].Value.Trim() }
    }
    return ''
}

$checks = [ordered]@{}
$issues = New-Object System.Collections.Generic.List[string]

Write-Log '=== trading path verify start ==='

# 1) Jarvis health
$h = Test-Http 'http://127.0.0.1:8000/health'
$checks['jarvis_health'] = $h
if (-not $h.ok) { $issues.Add("jarvis health: $($h.detail)") } else { Write-Log "OK jarvis health" }

# 2) Port listen
$portOk = [bool](Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
$checks['jarvis_port_8000'] = @{ ok = $portOk; detail = if ($portOk) { 'listening' } else { 'not listening' } }
if (-not $portOk) { $issues.Add('nothing listening on :8000') } else { Write-Log 'OK port 8000 listening' }

# 3) Ngrok
$ngrokProc = Get-Process -Name ngrok -ErrorAction SilentlyContinue | Select-Object -First 1
$publicBase = Get-NgrokPublicBase
$ngrokOk = [bool]$ngrokProc -and ($publicBase -ne '')
$checks['ngrok'] = @{ ok = $ngrokOk; detail = if ($publicBase) { $publicBase } else { 'no public url' }; pid = if ($ngrokProc) { $ngrokProc.Id } else { $null } }
if (-not $ngrokOk) { $issues.Add("ngrok: $($checks['ngrok'].detail)") } else { Write-Log "OK ngrok $publicBase" }

# 4) Local webhook
$secret = Get-TomlString 'webhook_secret'
$localWebhook = 'http://127.0.0.1:8000/api/trading/webhook/tradingview'
if ($secret) { $localWebhook = "${localWebhook}?secret=$secret" }
$lw = Test-Webhook $localWebhook
$checks['webhook_local'] = @{ ok = $lw.ok; detail = $lw.detail }
if (-not $lw.ok) { $issues.Add("local webhook: $($lw.detail)") } else { Write-Log 'OK local webhook' }

# 5) Public webhook via ngrok
if ($publicBase) {
    $pubWebhook = "$($publicBase.TrimEnd('/'))/api/trading/webhook/tradingview"
    if ($secret) { $pubWebhook = "${pubWebhook}?secret=$secret" }
    $pw = Test-Webhook $pubWebhook
    $checks['webhook_public'] = @{ ok = $pw.ok; detail = $pw.detail }
    if (-not $pw.ok) { $issues.Add("public webhook: $($pw.detail)") } else { Write-Log 'OK public webhook' }
} else {
    $checks['webhook_public'] = @{ ok = $false; detail = 'skipped - no public base' }
    $issues.Add('public webhook skipped - no ngrok base')
}

# 6) Live session + supervisor (OJ-only stack)
$env:JARVIS_TRADING_LOCKED = '1'
$env:PYTHONPATH = "$Root;$Root\src"
$sessionJson = & $Python -c @"
import json
from pathlib import Path
from trading_research.jarvis_locked import get_jarvis_settings
from trading_research.config.settings import get_settings
from trading_research.live.manual_orders import is_live_session_running
get_jarvis_settings()
s = get_settings()
d = Path(s.data_dir)
sup = {}
sp = d / 'live_supervisor_state.json'
if sp.is_file():
    try:
        sup = json.loads(sp.read_text(encoding='utf-8'))
    except Exception:
        pass
print(json.dumps({
    'session_running': bool(is_live_session_running(d)),
    'supervisor_running': bool(sup.get('running')),
    'supervisor_note': str(sup.get('note') or '')[:180],
    'equity': float((json.loads((d/'live_ledger.json').read_text(encoding='utf-8')).get('equity') or 0)) if (d/'live_ledger.json').is_file() else None,
}))
"@ 2>$null

try {
    $sess = $sessionJson | ConvertFrom-Json
    $checks['live_session'] = @{ ok = [bool]$sess.session_running; detail = "running=$($sess.session_running)" }
    $checks['live_supervisor'] = @{ ok = [bool]$sess.supervisor_running; detail = [string]$sess.supervisor_note }
    $checks['equity'] = @{ ok = $true; detail = [string]$sess.equity }
    if (-not $sess.session_running) { $issues.Add('live paper session not running') } else { Write-Log 'OK live session' }
    if (-not $sess.supervisor_running) { $issues.Add('live supervisor not running') } else { Write-Log 'OK live supervisor' }
} catch {
    $checks['live_session'] = @{ ok = $false; detail = "parse failed: $sessionJson" }
    $issues.Add('could not read live session state')
}

$ok = ($issues.Count -eq 0)
$result = [ordered]@{
    ok = $ok
    checked_at = (Get-Date).ToString('o')
    issues = @($issues)
    checks = $checks
}
$result | ConvertTo-Json -Depth 6 | Set-Content -Path $ResultFile -Encoding UTF8

if ($ok) {
    Write-Log 'PASS - all trading paths OK'
} else {
    Write-Log ('FAIL - ' + ($issues -join '; '))
}

if ($Fix -and -not $ok) {
    Write-Log 'FIX requested - attempting recovery'
    Set-Location $Root
    if (-not $checks['jarvis_health'].ok -or -not $checks['jarvis_port_8000'].ok) {
        Write-Log 'Restarting Jarvis...'
        & (Join-Path $Root 'scripts\start-jarvis.ps1') 2>&1 | ForEach-Object { Write-Log $_ }
    }
    if (-not $checks['ngrok'].ok -or -not $checks['webhook_public'].ok) {
        Write-Log 'Restarting TradingView tunnel...'
        & (Join-Path $Root 'scripts\start-tradingview-tunnel.ps1') -Provider ngrok 2>&1 | ForEach-Object { Write-Log $_ }
    }
    if (-not $checks['live_session'].ok -or -not $checks['live_supervisor'].ok) {
        Write-Log 'Restarting live trading stack...'
        & (Join-Path $Root 'scripts\restart-live-trading-clean.ps1') 2>&1 | ForEach-Object { Write-Log $_ }
    }
    Write-Log 'Re-check after fix...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -Quiet
    exit $LASTEXITCODE
}

if ($ok) { exit 0 } else { exit 1 }
