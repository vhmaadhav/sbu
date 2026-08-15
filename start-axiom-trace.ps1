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

if (-not $SkipInstall) {
    Push-Location $backendRoot
    try { & $uv sync --frozen --python 3.12 } finally { Pop-Location }

    if (-not (Test-Path -LiteralPath (Join-Path $webRoot "node_modules\next"))) {
        Push-Location $webRoot
        try {
            if ($webCommand.Name -eq "bun") { & $webCommand.Path install --frozen-lockfile }
            elseif ($webCommand.Name -eq "pnpm") { & $webCommand.Path install --no-lockfile }
            else { & $webCommand.Path install }
        } finally { Pop-Location }
    }
}

$backend = Start-Process -FilePath $uv `
    -ArgumentList @("run", "--frozen", "--python", "3.12", "python", "-m", "study_buddy") `
    -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runRoot "backend.out.log") `
    -RedirectStandardError (Join-Path $runRoot "backend.err.log")

$webArgs = if ($webCommand.Name -eq "bun") { @("run", "dev") } else { @("run", "dev") }
$web = Start-Process -FilePath $webCommand.Path -ArgumentList $webArgs `
    -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runRoot "web.out.log") `
    -RedirectStandardError (Join-Path $runRoot "web.err.log")

Set-Content -LiteralPath (Join-Path $runRoot "backend.pid") -Value $backend.Id
Set-Content -LiteralPath (Join-Path $runRoot "web.pid") -Value $web.Id

if (-not (Wait-ForUrl "http://127.0.0.1:8010/api/health" 60)) {
    throw "The API did not become ready. See .run/backend.err.log."
}
if (-not (Wait-ForUrl "http://127.0.0.1:3000" 60)) {
    throw "The web interface did not become ready. See .run/web.err.log."
}

Write-Host "Axiom Trace is ready." -ForegroundColor Green
Write-Host "Web: http://127.0.0.1:3000"
Write-Host "API: http://127.0.0.1:8010/api/docs"
Write-Host "Stop: .\stop-axiom-trace.ps1"
