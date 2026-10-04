# 不启动或停止真实服务：仅加载函数，并拦截系统查询、taskkill 与 PID 文件访问。
$ErrorActionPreference = 'Stop'
$sourcePath = Join-Path (Split-Path -Parent $PSScriptRoot) 'start-backend.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput(
    (Get-Content -LiteralPath $sourcePath -Raw -Encoding UTF8), [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) { throw $parseErrors[0] }
foreach ($name in @('Get-BackendServiceName', 'ConvertTo-ServiceRecord', 'Test-ServiceIdentity', 'Stop-ServiceProcess', 'Get-StrayProcesses', 'Invoke-BackendStop')) {
    $node = $ast.Find({ param($entry)
        $entry -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $entry.Name -eq $name
    }, $true)
    if (-not $node) { throw "找不到函数 $name" }
    Invoke-Expression $node.Extent.Text
}

$PythonExe = 'C:\review workspace\apps\api\.venv\Scripts\python.exe'
$PidFile = 'test-only-no-file'
$script:processes = @()
$script:state = $null
$script:killed = @()
$script:passed = 0
function Get-CimInstance {
    param($ClassName, $Filter, $ErrorAction)
    if ($Filter -match '^ProcessId = (\d+)$') {
        $id = [int]$Matches[1]
        return $script:processes | Where-Object { $_.ProcessId -eq $id }
    }
    return $script:processes
}
function Get-TrackedState { return $script:state }
function Test-Path { return $false }
function taskkill {
    $script:killed += ,@($args)
    $global:LASTEXITCODE = 0
}
function Assert-True {
    param([bool]$Value, [string]$Message)
    if (-not $Value) { throw $Message }
    $script:passed += 1
}
function New-FakeProcess {
    param([string]$Arguments = '-m uvicorn tender.api.app:app --port 8300')
    [pscustomobject]@{
        ProcessId = 1234
        ExecutablePath = $PythonExe
        CommandLine = '"' + $PythonExe + '" ' + $Arguments
        CreationDate = [datetime]'2026-10-04T12:00:00.123456Z'
    }
}

foreach ($entry in @(
    @('api', '-m uvicorn tender.api.app:app --port 8300'),
    @('worker', '-m celery -A tender.worker.celery_app worker -P threads'),
    @('beat', '-m celery -A tender.worker.celery_app beat')
)) {
    $process = New-FakeProcess -Arguments $entry[1]
    $script:processes = @($process)
    $record = ConvertTo-ServiceRecord -ProcessInfo $process
    Assert-True ($record.name -eq $entry[0]) "服务类型识别错误：$($entry[0])"
    # 身份信息经过真实 JSON 序列化后仍须可匹配，避免 PID 文件写出后无法停止。
    $roundTrip = $record | ConvertTo-Json | ConvertFrom-Json
    Assert-True (Test-ServiceIdentity -Service $roundTrip) '合法进程身份未通过'
    Assert-True (Stop-ServiceProcess -Service $roundTrip) '合法进程无法停止'
}
Assert-True ($script:killed.Count -eq 3) '合法的三个服务应各终止一次'

$process = New-FakeProcess
$record = ConvertTo-ServiceRecord -ProcessInfo $process
$script:processes = @($process)
$script:killed = @()
$process.CreationDate = $process.CreationDate.AddSeconds(1)
Assert-True (-not (Stop-ServiceProcess -Service $record)) '同命令但创建时间改变的复用 PID 不能终止'
$process.CreationDate = [datetime]'2026-10-04T12:00:00.123456Z'
$process.ExecutablePath = 'C:\other\python.exe'
Assert-True (-not (Stop-ServiceProcess -Service $record)) '其它解释器不能终止'
$process.ExecutablePath = $PythonExe
$process.CommandLine = '"' + $PythonExe + '" -m celery -A other.app worker'
Assert-True (-not (Stop-ServiceProcess -Service $record)) '其它 Celery 应用不能终止'
$process.CommandLine = $record.commandLine + ' --reload'
Assert-True (-not (Stop-ServiceProcess -Service $record)) '命令行发生变化的进程不能当作原实例'
$script:processes = @()
Assert-True (-not (Stop-ServiceProcess -Service $record)) '已退出的进程不能终止'
$legacy = [pscustomobject]@{ name = 'api'; pid = 1234 }
Assert-True (-not (Stop-ServiceProcess -Service $legacy)) '缺少创建时间的旧 PID 不能直接终止'
Assert-True ($script:killed.Count -eq 0) '身份检查失败时不应调用 taskkill'

# 复现审查中的误杀路径：旧文件指向已复用的 PowerShell PID，整条停止流程都应跳过。
$unrelated = New-FakeProcess
$unrelated.ExecutablePath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
$unrelated.CommandLine = 'powershell.exe'
$script:processes = @($unrelated)
$script:state = [pscustomobject]@{ services = @($record) }
Invoke-BackendStop | Out-Null
Assert-True ($script:killed.Count -eq 0) '停止流程误杀了复用 PID 的无关进程'

# 旧格式中仍在运行的本项目服务可由现场扫描重新识别，再按新身份二次核验后停止。
$script:processes = @(New-FakeProcess)
$script:state = [pscustomobject]@{ services = @($legacy) }
Invoke-BackendStop | Out-Null
Assert-True ($script:killed.Count -eq 1) '旧记录中的合法服务未通过现场扫描恢复管理'
Write-Host "$script:passed 项进程身份回归检查通过（未终止真实进程）"
