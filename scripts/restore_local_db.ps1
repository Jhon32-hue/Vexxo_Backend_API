param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

if (-not $ConfirmRestore) {
    throw "La restauracion reemplaza datos locales. Repite con -ConfirmRestore."
}
$resolvedBackup = [System.IO.Path]::GetFullPath($BackupPath)
if (-not (Test-Path -LiteralPath $resolvedBackup -PathType Leaf)) {
    throw "Backup no encontrado: $resolvedBackup"
}

docker compose -f docker-compose.local.yml cp $resolvedBackup db:/tmp/vexxo-restore.dump
if ($LASTEXITCODE -ne 0) { throw "No fue posible copiar el backup al contenedor." }
docker compose -f docker-compose.local.yml exec -T db pg_restore -U vexxo -d vexxo --clean --if-exists --no-owner /tmp/vexxo-restore.dump
if ($LASTEXITCODE -ne 0) { throw "pg_restore fallo con codigo $LASTEXITCODE" }
Write-Host "Restauracion local completada desde: $resolvedBackup"
