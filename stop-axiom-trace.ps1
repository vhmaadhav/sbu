[CmdletBinding()]
param()

$runRoot = Join-Path (Resolve-Path -LiteralPath $PSScriptRoot).Path ".run"
foreach ($name in @("backend", "web")) {
    $pidFile = Join-Path $runRoot "$name.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { continue }
    $processId = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue
    if ($processId -and $processId -match '^\d+$') {
        & taskkill.exe /PID ([int]$processId) /T /F 2>$null | Out-Null
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "Axiom Trace services stopped."
