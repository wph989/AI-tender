<#
后端统一离线验证入口。协议与装配由 mypy 检查，pytest 中的契约测试也会独立验证该门禁。
#>
$ErrorActionPreference = 'Stop'
$ApiRoot = Join-Path $PSScriptRoot '../apps/api'
$PythonExe = Join-Path $ApiRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw '缺少后端虚拟环境，请先在 apps/api 执行 uv sync --group dev。'
}

Push-Location $ApiRoot
try {
    & $PythonExe -X utf8 -m ruff check src tests
    if ($LASTEXITCODE -ne 0) { throw 'Ruff 检查失败' }
    # 用同一解释器启用 UTF-8，避免 Windows 控制台把中文契约名称输出成乱码。
    & $PythonExe -X utf8 -c 'from importlinter.cli import lint_imports_command; lint_imports_command()' --config pyproject.toml
    if ($LASTEXITCODE -ne 0) { throw '架构导入检查失败' }
    & $PythonExe -X utf8 -m pytest tests/unit tests/contract -q
    if ($LASTEXITCODE -ne 0) { throw '离线测试或协议类型检查失败' }
}
finally {
    Pop-Location
}
