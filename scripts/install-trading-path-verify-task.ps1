# Install weekday scheduled tasks: verify OJ trading paths at 9:00, 12:00, 14:00 local time.
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$Script = Join-Path $Root 'scripts\verify-trading-paths.ps1'
$TaskPrefix = 'OpenJarvis-TradingPathVerify'

if (-not (Test-Path $Script)) {
    throw "Missing verify script: $Script"
}

# Auto-fix on failure so paths stay live during the session.
$cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`" -Fix -Quiet"

$times = @(
    @{ Name = "$TaskPrefix-0900"; Time = '09:00' },
    @{ Name = "$TaskPrefix-1200"; Time = '12:00' },
    @{ Name = "$TaskPrefix-1400"; Time = '14:00' }
)

foreach ($t in $times) {
    cmd /c "schtasks /Delete /TN `"$($t.Name)`" /F >nul 2>&1"
    # Weekdays only (MON-FRI)
    $out = cmd /c "schtasks /Create /F /TN `"$($t.Name)`" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST $($t.Time) /TR `"$cmd`" /RL LIMITED" 2>&1 | Out-String
    Write-Host $out.Trim()
    Write-Host "Installed $($t.Name) at $($t.Time) weekdays"
}

Write-Host ''
Write-Host 'Verify script:  ' $Script
Write-Host 'Log:            ' (Join-Path $env:USERPROFILE '.openjarvis\trading-path-verify.log')
Write-Host 'Last result:    ' (Join-Path $env:USERPROFILE '.openjarvis\trading-path-verify.json')
Write-Host 'Run once now:   powershell -File "' $Script '"'
Write-Host 'Remove all:     schtasks /Delete /TN OpenJarvis-TradingPathVerify-0900 /F  (and -1200 / -1400)'
