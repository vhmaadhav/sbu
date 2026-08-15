[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$backendRoot = Join-Path $projectRoot "backend"
$webRoot = Join-Path $projectRoot "web"
$runRoot = Join-Path $projectRoot ".run"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$env:CI = "true"
$env:NEXT_TELEMETRY_DISABLED = "1"

function Require-Command([string]$Name, [string]$Help) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "$Name is required. $Help"
    }
    return $command.Source
}

function Wait-ForUrl([string]$Url, [int]$Seconds = 45) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -lt 500) { return $true }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    return $false
}

function Stop-ProcessTree([int]$ProcessId) {
    & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
}

$uv = Require-Command "uv" "Install it from https://docs.astral.sh/uv/."
$webCommand = $null
foreach ($candidate in @("pnpm", "bun", "npm")) {
    $found = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($found) {
        $webCommand = @{ Name = $candidate; Path = $found.Source }
        break
    }
}
if (-not $webCommand) {
    throw "pnpm, bun, or npm is required to run the web interface."
}

# Codex Desktop exposes pnpm through a bundled fallback wrapper. When that
# wrapper is selected, make its sibling Node runtime visible to child scripts.
if (-not (Get-Command node -ErrorAction SilentlyContinue) -and $webCommand.Name -eq "pnpm") {
    $dependencyRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $webCommand.Path))
    $bundledNodeBin = Join-Path $dependencyRoot "node\bin"
    if (Test-Path -LiteralPath (Join-Path $bundledNodeBin "node.exe")) {
        $env:PATH = "$bundledNodeBin;$env:PATH"
    }
}

if (-not $SkipInstall) {
    Push-Location $backendRoot
    try { & $uv sync --frozen --python 3.12 } finally { Pop-Location }

    if (-not (Test-Path -LiteralPath (Join-Path $webRoot "node_modules\next"))) {
        Push-Location $webRoot
        try {
            if ($webCommand.Name -eq "bun") { & $webCommand.Path install --frozen-lockfile }
            elseif ($webCommand.Name -eq "pnpm") { & $webCommand.Path install --frozen-lockfile }
            else { & $webCommand.Path ci }
        } finally { Pop-Location }
    }
}

$backend = $null
$web = $null
try {
    $backend = Start-Process -FilePath $uv `
        -ArgumentList @("run", "--frozen", "--python", "3.12", "python", "-m", "study_buddy") `
        -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runRoot "backend.out.log") `
        -RedirectStandardError (Join-Path $runRoot "backend.err.log")

    $web = Start-Process -FilePath $webCommand.Path -ArgumentList @("run", "dev") `
        -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runRoot "web.out.log") `
        -RedirectStandardError (Join-Path $runRoot "web.err.log")

    Set-Content -LiteralPath (Join-Path $runRoot "backend.pid") -Value $backend.Id
    Set-Content -LiteralPath (Join-Path $runRoot "web.pid") -Value $web.Id

    if (-not (Wait-ForUrl "http://127.0.0.1:8010/api/health/live" 60)) {
        throw "The API did not become ready. See .run/backend.err.log."
    }
    if (-not (Wait-ForUrl "http://127.0.0.1:3000" 60)) {
        throw "The web interface did not become ready. See .run/web.err.log."
    }
} catch {
    foreach ($process in @($web, $backend)) {
        if ($process) { Stop-ProcessTree $process.Id }
    }
    foreach ($pidFile in @("backend.pid", "web.pid")) {
        Remove-Item -LiteralPath (Join-Path $runRoot $pidFile) -Force -ErrorAction SilentlyContinue
    }
    throw
}

Write-Host "Axiom Trace is ready." -ForegroundColor Green
Write-Host "Web: http://127.0.0.1:3000"
Write-Host "API: http://127.0.0.1:8010/api/docs"
Write-Host "Stop: .\stop-axiom-trace.ps1"
