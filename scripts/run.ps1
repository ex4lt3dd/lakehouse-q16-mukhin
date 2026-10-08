param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& $PSScriptRoot/start.ps1 -Python $Python
foreach ($action in 'build','benchmark','evolution','travel','measure','validate') {
    & $Python -X utf8 scripts/lab.py $action
    if ($LASTEXITCODE -ne 0) { throw "Ошибка этапа $action" }
}
& $Python -X utf8 scripts/setup_superset.py
if ($LASTEXITCODE -ne 0) { throw 'Ошибка подключения Superset' }
