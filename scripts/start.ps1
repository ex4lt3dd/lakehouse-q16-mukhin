param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.env')) {
    $names = 'S3_ACCESS_KEY','S3_SECRET_KEY','PG_PASSWORD','PG_ENCRYPTION_KEY','SUPERSET_SECRET_KEY','SUPERSET_ADMIN_PASSWORD'
    $lines = foreach ($name in $names) {
        $bytes = New-Object byte[] 24
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $value = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        "$name=$value"
    }
    [IO.File]::WriteAllLines((Join-Path $PWD '.env'), $lines)
}
docker compose --progress quiet up -d minio postgres migrate lakekeeper buckets trino
if ($LASTEXITCODE -ne 0) { throw 'Не удалось запустить основной стек' }
& $Python -X utf8 scripts/lab.py provision
if ($LASTEXITCODE -ne 0) { throw 'Не удалось зарегистрировать warehouse' }
docker compose --progress quiet up -d --build superset
if ($LASTEXITCODE -ne 0) { throw 'Не удалось запустить Superset' }
