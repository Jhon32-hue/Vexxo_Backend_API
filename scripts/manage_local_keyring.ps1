param(
    [ValidateSet('Initialize', 'Rotate', 'Retire', 'Restore', 'Status')]
    [string]$Action = 'Status',
    [string]$EnvFile = '.env.local',
    [string]$BackupFile = '.runtime/security/local-keyring.dpapi',
    [string]$Version = '',
    [switch]$ConfirmRetire
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envPath = [IO.Path]::GetFullPath((Join-Path $root $EnvFile))
$backupPath = [IO.Path]::GetFullPath((Join-Path $root $BackupFile))
$entropy = [Text.Encoding]::UTF8.GetBytes('vexxo-local-keyring-v1')

$isWindowsHost = $env:OS -eq 'Windows_NT' -or $PSVersionTable.Platform -eq 'Win32NT'
if (-not $isWindowsHost) {
    throw 'El respaldo DPAPI del keyring local solo esta soportado en Windows.'
}
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "No existe $envPath. Crea .env.local antes de administrar el keyring."
}

Add-Type -AssemblyName System.Security

function Read-EnvLines {
    return [Collections.Generic.List[string]](Get-Content -LiteralPath $envPath)
}

function Read-EnvValue([Collections.Generic.List[string]]$Lines, [string]$Name) {
    $prefix = "$Name="
    foreach ($line in $Lines) {
        if ($line.StartsWith($prefix, [StringComparison]::Ordinal)) {
            return $line.Substring($prefix.Length)
        }
    }
    return ''
}

function Set-EnvValue(
    [Collections.Generic.List[string]]$Lines,
    [string]$Name,
    [string]$Value
) {
    $prefix = "$Name="
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index].StartsWith($prefix, [StringComparison]::Ordinal)) {
            $Lines[$index] = "$prefix$Value"
            return
        }
    }
    $Lines.Add("$prefix$Value")
}

function New-KeyMaterial {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes)
}

function Read-Keyring([Collections.Generic.List[string]]$Lines) {
    $raw = Read-EnvValue $Lines 'VEXXO_LOCAL_SECURITY_ENCRYPTION_KEYS_JSON'
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq '{}') {
        return [ordered]@{}
    }
    $parsed = $raw | ConvertFrom-Json
    $result = [ordered]@{}
    foreach ($property in ($parsed.PSObject.Properties | Sort-Object Name)) {
        $result[$property.Name] = [string]$property.Value
    }
    return $result
}

function Write-ProtectedBackup([string]$ActiveVersion, [hashtable]$Keys) {
    $directory = Split-Path -Parent $backupPath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $payload = [ordered]@{
        schema_version = 1
        active_version = $ActiveVersion
        keys = $Keys
        backed_up_at = [DateTimeOffset]::UtcNow.ToString('O')
    } | ConvertTo-Json -Compress
    $protected = [Security.Cryptography.ProtectedData]::Protect(
        [Text.Encoding]::UTF8.GetBytes($payload),
        $entropy,
        [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    [IO.File]::WriteAllBytes($backupPath, $protected)
}

function Write-Keyring(
    [Collections.Generic.List[string]]$Lines,
    [string]$ActiveVersion,
    [hashtable]$Keys
) {
    $json = $Keys | ConvertTo-Json -Compress
    Set-EnvValue $Lines 'VEXXO_LOCAL_SECURITY_ENCRYPTION_ACTIVE_KEY_VERSION' $ActiveVersion
    Set-EnvValue $Lines 'VEXXO_LOCAL_SECURITY_ENCRYPTION_KEYS_JSON' $json
    Write-ProtectedBackup $ActiveVersion $Keys
    $temporary = "$envPath.tmp"
    [IO.File]::WriteAllLines($temporary, $Lines, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $envPath -Force
}

$lines = Read-EnvLines
$keys = Read-Keyring $lines
$active = Read-EnvValue $lines 'VEXXO_LOCAL_SECURITY_ENCRYPTION_ACTIVE_KEY_VERSION'

switch ($Action) {
    'Initialize' {
        if ($keys.Count -gt 0) {
            throw 'El keyring ya existe. Usa Rotate para agregar una version.'
        }
        $keys['v1'] = New-KeyMaterial
        Write-Keyring $lines 'v1' $keys
        Write-Output 'keyring_initialized=true active_version=v1 versions=v1'
    }
    'Rotate' {
        if ($keys.Count -eq 0) {
            throw 'Inicializa el keyring antes de rotarlo.'
        }
        $numbers = @($keys.Keys | ForEach-Object {
            if ($_ -match '^v([0-9]+)$') { [int]$matches[1] }
        })
        $next = if ($numbers.Count) { ($numbers | Measure-Object -Maximum).Maximum + 1 } else { 1 }
        $version = "v$next"
        $keys[$version] = New-KeyMaterial
        Write-Keyring $lines $version $keys
        Write-Output "keyring_rotated=true active_version=$version versions=$($keys.Keys -join ',')"
    }
    'Retire' {
        if (-not $ConfirmRetire) {
            throw 'Retire exige -ConfirmRetire despues de ejecutar key_retirement_check.'
        }
        if ([string]::IsNullOrWhiteSpace($Version) -or -not $keys.Contains($Version)) {
            throw 'Indica una version configurada mediante -Version.'
        }
        if ($Version -eq $active) {
            throw 'No se puede retirar la version activa.'
        }
        if (Test-Path -LiteralPath $backupPath) {
            $archiveDirectory = Join-Path (Split-Path -Parent $backupPath) 'retired'
            New-Item -ItemType Directory -Path $archiveDirectory -Force | Out-Null
            $stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss')
            Copy-Item -LiteralPath $backupPath -Destination (Join-Path $archiveDirectory "$Version-$stamp.dpapi")
        }
        $keys.Remove($Version)
        Write-Keyring $lines $active $keys
        Write-Output "keyring_retired=true retired_version=$Version active_version=$active versions=$($keys.Keys -join ',')"
    }
    'Restore' {
        if (-not (Test-Path -LiteralPath $backupPath)) {
            throw "No existe respaldo DPAPI en $backupPath."
        }
        $plaintext = [Security.Cryptography.ProtectedData]::Unprotect(
            [IO.File]::ReadAllBytes($backupPath),
            $entropy,
            [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        $payload = [Text.Encoding]::UTF8.GetString($plaintext) | ConvertFrom-Json
        $restored = [ordered]@{}
        foreach ($property in $payload.keys.PSObject.Properties) {
            $restored[$property.Name] = [string]$property.Value
        }
        Write-Keyring $lines ([string]$payload.active_version) $restored
        Write-Output "keyring_restored=true active_version=$($payload.active_version) versions=$($restored.Keys -join ',')"
    }
    'Status' {
        $backupAvailable = Test-Path -LiteralPath $backupPath
        Write-Output "configured=$($keys.Count -gt 0) active_version=$active versions=$($keys.Keys -join ',') backup_available=$backupAvailable"
    }
}
