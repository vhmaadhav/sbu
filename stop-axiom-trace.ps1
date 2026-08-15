[CmdletBinding()]
param()

$runRoot = Join-Path (Resolve-Path -LiteralPath $PSScriptRoot).Path ".run"
foreach ($name in @("backend", "web")) {
    $pidFile = Join-Path $runRoot "$name.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { continue }
    $processId = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue
    if ($processId -and $processId -match '^\d+$') {
        Stop-Process -Id ([int]$processId) -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "Axiom Trace services stopped."
