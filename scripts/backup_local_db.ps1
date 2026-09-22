param(
    [string]$OutputDirectory = ".runtime\backups"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

$resolvedDirectory = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDirectory))
$runtimeRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot ".runtime"))
if (-not $resolvedDirectory.StartsWith($runtimeRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "El backup debe quedar dentro de $runtimeRoot"
}

New-Item -ItemType Directory -Force -Path $resolvedDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $resolvedDirectory "vexxo-local-$stamp.dump"

docker compose -f docker-compose.local.yml exec -T db pg_dump -U vexxo -d vexxo -Fc -f /tmp/vexxo-local.dump
if ($LASTEXITCODE -ne 0) { throw "pg_dump fallo con codigo $LASTEXITCODE" }
docker compose -f docker-compose.local.yml cp db:/tmp/vexxo-local.dump $target
if ($LASTEXITCODE -ne 0) { throw "No fue posible copiar el backup desde el contenedor." }
Write-Host "Backup creado: $target"
