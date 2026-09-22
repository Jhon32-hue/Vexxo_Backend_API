param(
    [ValidateSet("smoke", "baseline", "stress", "authenticated", "authenticated-stress")]
    [string]$Profile = "smoke",
    [string]$Target = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LoadRoot = Join-Path $RepoRoot "tests\load"
$ReportRoot = Join-Path $RepoRoot ".runtime\artillery"
$Artillery = Join-Path $LoadRoot "node_modules\.bin\artillery.cmd"

if (-not (Test-Path -LiteralPath $Artillery)) {
    throw "Artillery no esta instalado. Ejecuta: npm install --prefix tests/load --no-audit --no-fund"
}
if ($Profile.StartsWith("authenticated") -and [string]::IsNullOrWhiteSpace($env:ARTILLERY_ACCESS_TOKEN)) {
    throw "ARTILLERY_ACCESS_TOKEN es requerido para el perfil authenticated."
}

try {
    $health = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "$Target/readyz/"
} catch {
    throw "El backend no esta listo en $Target. $($_.Exception.Message)"
}
if ($health.StatusCode -ne 200) {
    throw "Readiness devolvio HTTP $($health.StatusCode)."
}

New-Item -ItemType Directory -Force -Path $ReportRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$report = Join-Path $ReportRoot "$Profile-$stamp.json"
$script = if ($Profile.StartsWith("authenticated")) {
    Join-Path $LoadRoot "artillery.authenticated.yml"
} else {
    Join-Path $LoadRoot "artillery.public.yml"
}

$arguments = @("run", "--target", $Target, "--output", $report)
$environment = if ($Profile -eq "authenticated") { "baseline" } elseif ($Profile -eq "authenticated-stress") { "stress" } else { $Profile }
$arguments += @("--environment", $environment)
$arguments += $script

& $Artillery @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Artillery fallo con codigo $LASTEXITCODE. Reporte: $report"
}
Write-Host "Reporte Artillery: $report"
