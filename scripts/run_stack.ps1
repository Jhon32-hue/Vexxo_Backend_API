param(
    [ValidateSet('local')]
    [string]$Environment = 'local',

    [ValidateSet('up', 'down', 'restart', 'logs', 'status', 'verify', 'migrate', 'check', 'test', 'security-status', 'key-rotation-status', 'rotate-keys')]
    [string]$Action = 'up',

    [ValidateSet('core', 'auth', 'accounts', 'alerts', 'transactions', 'payments', 'debts', 'planning', 'documents', 'full')]
    [string]$Slice = 'core',

    [switch]$Build,
    [switch]$Follow,
    [switch]$Performance,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$composeFile = Join-Path $root 'docker-compose.local.yml'
$performanceComposeFile = Join-Path $root 'docker-compose.performance.yml'
$envFile = Join-Path $root '.env.local'
if (-not (Test-Path -LiteralPath $envFile)) {
    $envFile = Join-Path $root '.env.local.example'
}

function Initialize-LocalBuildCertificate {
    if ($env:VEXXO_LOCAL_CA_CERT_PATH) {
        if (-not (Test-Path -LiteralPath $env:VEXXO_LOCAL_CA_CERT_PATH)) {
            throw "VEXXO_LOCAL_CA_CERT_PATH no existe: $($env:VEXXO_LOCAL_CA_CERT_PATH)"
        }
        $env:VEXXO_LOCAL_CA_CERT_PATH = (Resolve-Path -LiteralPath $env:VEXXO_LOCAL_CA_CERT_PATH).Path
        return
    }

    $certificateDirectory = Join-Path $root '.runtime\docker'
    $certificatePath = Join-Path $certificateDirectory 'local-ca.crt'
    New-Item -ItemType Directory -Path $certificateDirectory -Force | Out-Null

    $localCertificate = Get-ChildItem -Path Cert:\CurrentUser\Root |
        Where-Object { $_.Subject -like 'CN=AVG Web/Mail Shield Root,*' } |
        Select-Object -First 1

    if ($localCertificate) {
        $certificateBytes = $localCertificate.Export(
            [System.Security.Cryptography.X509Certificates.X509ContentType]::Cert
        )
        $certificateBase64 = [Convert]::ToBase64String(
            $certificateBytes,
            [Base64FormattingOptions]::InsertLineBreaks
        )
        $certificatePem = "-----BEGIN CERTIFICATE-----`r`n$certificateBase64`r`n-----END CERTIFICATE-----`r`n"
        [IO.File]::WriteAllText($certificatePath, $certificatePem, [Text.Encoding]::ASCII)
    }
    else {
        [IO.File]::WriteAllBytes($certificatePath, [byte[]]@())
    }

    $env:VEXXO_LOCAL_CA_CERT_PATH = $certificatePath
}

Initialize-LocalBuildCertificate

$sliceServices = @{
    core = @('db', 'api')
    auth = @('db', 'api', 'identity-outbox')
    accounts = @('db', 'api', 'accounts-outbox', 'accounts-sync-worker', 'accounts-intelligence-worker')
    alerts = @('db', 'api', 'alerts-outbox', 'alerts-ai-worker')
    transactions = @('db', 'api', 'transactions-outbox', 'transactions-voice-worker')
    payments = @('db', 'api', 'payments-outbox', 'scheduler-local')
    debts = @('db', 'api', 'domain-outbox', 'scheduler-local')
    planning = @('db', 'api', 'domain-outbox', 'scheduler-local')
    documents = @('db', 'clamav', 'api', 'documents-ocr-worker', 'domain-outbox', 'scheduler-local')
    full = @(
        'db', 'api', 'identity-outbox', 'accounts-outbox',
        'accounts-sync-worker', 'accounts-intelligence-worker',
        'alerts-outbox', 'alerts-ai-worker', 'transactions-outbox',
        'transactions-voice-worker', 'clamav', 'documents-ocr-worker', 'payments-outbox', 'domain-outbox',
        'scheduler-local'
    )
}

function Invoke-Compose([string[]]$Arguments) {
    $composeArguments = @('--env-file', $envFile, '-f', $composeFile)
    if ($Performance) {
        $composeArguments += @('-f', $performanceComposeFile)
    }
    & docker compose @composeArguments @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose fallo con codigo $LASTEXITCODE"
    }
}

function Test-LocalMobileApiHost {
    $composeArguments = @('--env-file', $envFile, '-f', $composeFile)
    if ($Performance) {
        $composeArguments += @('-f', $performanceComposeFile)
    }
    $portBindings = & docker compose @composeArguments port api 8000
    $composeExitCode = $LASTEXITCODE
    $portBinding = $portBindings | Select-Object -First 1
    if ($composeExitCode -ne 0 -or $portBinding -notmatch ':(\d+)$') {
        throw 'No fue posible resolver el puerto local del API.'
    }

    $hostPort = $Matches[1]
    $response = Invoke-WebRequest `
        -Uri "http://127.0.0.1:$hostPort/readyz/" `
        -Headers @{ Host = "10.0.2.2:$hostPort" } `
        -UseBasicParsing `
        -TimeoutSec 5
    if ($response.StatusCode -ne 200) {
        throw "Mobile host probe fallo con HTTP $($response.StatusCode)."
    }
    Write-Output "mobile_host_check=ok host=10.0.2.2:$hostPort"
}

function Get-TestModuleLabels {
    Get-ChildItem -LiteralPath $root -Recurse -File |
        Where-Object {
            ($_.Name -eq 'tests.py' -or $_.Name -like 'test_*.py') -and
            $_.FullName -notmatch '[\\/](\.git|\.venv|venv|env|enviroment)[\\/]'
        } |
        ForEach-Object {
            $relativePath = $_.FullName.Substring($root.Length + 1)
            (($relativePath -replace '\.py$', '') -replace '[\\/]', '.')
        } |
        Sort-Object -Unique
}

$services = $sliceServices[$Slice]
switch ($Action) {
    'up' {
        $up = @('up', '-d')
        if ($Build) { $up += '--build' }
        Invoke-Compose ($up + @('db'))
        $migrate = @('run', '--rm')
        if ($Build) { $migrate += '--build' }
        Invoke-Compose ($migrate + @('migrate'))
        Invoke-Compose ($up + $services)
        Test-LocalMobileApiHost
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'runtime_status', '--strict')
        if ($Performance) {
            Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'db_connection_budget', '--strict')
        }
    }
    'down' { Invoke-Compose @('down', '--remove-orphans') }
    'restart' { Invoke-Compose (@('restart') + $services) }
    'logs' {
        $arguments = @('logs')
        if ($Follow) { $arguments += '--follow' }
        Invoke-Compose ($arguments + $services)
    }
    'status' {
        Invoke-Compose @('ps')
        Test-LocalMobileApiHost
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'runtime_status', '--strict')
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'outbox_status')
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'worker_status')
        if ($Performance) {
            Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'db_connection_budget', '--strict')
        }
    }
    'verify' {
        Test-LocalMobileApiHost
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'check')
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'migrate', '--check')
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'makemigrations', '--check', '--dry-run')
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'runtime_status', '--strict')
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'security_activation_check')
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'json_field_audit', '--scan-data', '--strict')
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'api_filter_audit', '--strict')
        Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'open_banking_certification_status', '--strict')
    }
    'migrate' { Invoke-Compose @('run', '--rm', 'migrate') }
    'check' { Invoke-Compose (@('run', '--rm', 'api', 'python', 'manage.py', 'check') + $ExtraArgs) }
    'security-status' { Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'security_status') }
    'key-rotation-status' { Invoke-Compose @('exec', '-T', 'api', 'python', 'manage.py', 'key_rotation_status') }
    'rotate-keys' {
        Invoke-Compose (@('exec', '-T', 'api', 'python', 'manage.py', 'run_worker', 'security.key_rotation', '--loop') + $ExtraArgs)
    }
    'test' {
        $testArguments = @('run', '--rm', 'api', 'python', 'manage.py', 'test', '--keepdb', '--noinput')
        if ($ExtraArgs) {
            $testArguments += $ExtraArgs
        }
        else {
            $testArguments += @(Get-TestModuleLabels)
        }
        Invoke-Compose $testArguments
    }
}
