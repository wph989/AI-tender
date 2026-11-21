<#
PostgreSQL 集成验证入口。必须显式提供独立测试库连接串，避免误用本地业务库。
#>
$ErrorActionPreference = 'Stop'
$TestDatabaseUrl = $env:TENDER_TEST_DATABASE_URL
if ([string]::IsNullOrWhiteSpace($TestDatabaseUrl)) {
    throw '请先设置 TENDER_TEST_DATABASE_URL 指向独立 PostgreSQL 测试数据库。'
}

try {
    $DatabaseUri = [System.Uri]$TestDatabaseUrl
} catch {
    throw 'TENDER_TEST_DATABASE_URL 不是有效的 PostgreSQL URI。'
}
$DatabaseName = $DatabaseUri.AbsolutePath.Trim('/')
if ($DatabaseName -notmatch '(?i)(^|[_-])test([_-]|$)') {
    throw '测试数据库名称必须包含独立的 test 标记，例如 tender_test。'
}

$ApiRoot = Join-Path $PSScriptRoot '../apps/api'
$PythonExe = Join-Path $ApiRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw '缺少后端虚拟环境，请先在 apps/api 执行 uv sync --group dev。'
}

Push-Location $ApiRoot
try {
    $env:DATABASE_URL = $TestDatabaseUrl
    $env:TENDER_RUN_DB_TESTS = '1'
    & $PythonExe -X utf8 -m pytest tests/integration -q --tb=short
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL 集成验证失败' }
}
finally {
    Pop-Location
}
