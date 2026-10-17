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

# 执行真实的启动前主流程以约束检查顺序；所有进程、端口和文件操作仍由替身接管。
$statements = $ast.EndBlock.Statements
$begin = $statements | Where-Object {
    $_ -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $_.Left.Extent.Text -eq '$runningServices'
} | Select-Object -First 1
$end = $statements | Where-Object {
    $_ -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $_.Left.Extent.Text -eq '$started'
} | Select-Object -First 1
if (-not $begin -or -not $end) { throw '找不到启动前检查的边界' }
$preflightScript = [scriptblock]::Create((($statements | Where-Object {
    $_.Extent.StartOffset -ge $begin.Extent.StartOffset -and
    $_.Extent.StartOffset -lt $end.Extent.StartOffset
}).Extent.Text -join "`n"))

function Invoke-PreflightScenario {
    param([string]$OutputMode = 'file', [int]$ConfigExitCode = 0, [bool]$DirectoryFails = $false)
    $events = New-Object System.Collections.Generic.List[string]
    $PythonExe = 'Invoke-FakePython'
    $Force = $true
    $ApiPort = 8300
    function Get-TrackedState { return $null }
    function Get-StrayProcesses { return [pscustomobject]@{ ProcessId = 1234 } }
    function Invoke-FakePython {
        $events.Add('config')
        $global:LASTEXITCODE = $ConfigExitCode
        return (@{ directory = 'test-only-logs'; output = $OutputMode } | ConvertTo-Json)
    }
    function New-Item {
        $events.Add('directory')
        if ($DirectoryFails) { throw '模拟日志目录不可创建' }
    }
    function Invoke-BackendStop { $events.Add('stop') }
    function Wait-PortFree { return $true }
    function Get-NetTCPConnection { return $null }
    $failure = $null
    try { & $preflightScript } catch { $failure = $_ }
    return [pscustomobject]@{ Events = @($events.ToArray()); Failure = $failure }
}

foreach ($scenario in @(
    @{ OutputMode = 'stdout'; Expected = '隐藏窗口启动需要' },
    @{ ConfigExitCode = 1; Expected = '日志配置无效' },
    @{ DirectoryFails = $true; Expected = '模拟日志目录不可创建' }
)) {
    $expected = $scenario.Expected
    $scenario.Remove('Expected')
    $result = Invoke-PreflightScenario @scenario
    Assert-True ($null -ne $result.Failure) '无效的日志配置或目录必须阻止启动'
    Assert-True ($result.Failure.ToString().Contains($expected)) '应报告对应的预检失败原因'
    Assert-True ($result.Events -notcontains 'stop') '日志预检失败时 -Force 不能停止现有服务'
}
foreach ($mode in @('file', 'both')) {
    $result = Invoke-PreflightScenario -OutputMode $mode
    Assert-True ($null -eq $result.Failure) "$mode 模式预检不应失败"
    Assert-True (($result.Events -join ',') -eq 'config,directory,stop') '必须预检成功后才停止服务'
}
Write-Host "$script:passed 项进程身份与启动预检回归检查通过（未启停真实服务）"
