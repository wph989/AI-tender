<#
.SYNOPSIS
    一键启动 / 停止 / 查看后端进程：API、一个全队列 Celery Worker 与 Beat。

.DESCRIPTION
    把《本地启动指南》第 3.1-3.3 节的三条命令固化成一条。
    API、Worker 与 Beat 的职责，见指南第 1 节与
    docs/工程/10-技术选型与工程结构.md：API 只往数据库写 pending 的 job，
    beat 每秒向 Worker 投递调度消息，按配置中心的上限派发差额，worker 才是真正执行任务的一方。

    用法：
      .\scripts\start-backend.ps1            # 启动（已有活着的实例时拒绝重复启动）
      .\scripts\start-backend.ps1 -Force     # 先停干净再启动
      .\scripts\start-backend.ps1 -Status    # 只看进程与端口状态
      .\scripts\start-backend.ps1 -Stop      # 停止

.PARAMETER Stop
    停止后端。除 PID 记录里的进程外，还会按命令行清掉「在仓库目录下手敲启动」的同名进程，
    否则重复启动会出现两个 worker 抢同一个队列。

.PARAMETER Status
    只打印状态，不做任何启停。

.PARAMETER Force
    启动前先执行一次停止流程。

.PARAMETER TimeoutSeconds
    API 健康检查的等待上限（秒），默认 60；超时判定为启动失败，回滚本次已启动的进程。

.NOTES
    本文件必须保存为「UTF-8 带 BOM」：Windows PowerShell 5.1 在 GBK(936) 代码页下会把无 BOM
    的 UTF-8 中文按 GBK 解码，导致脚本直接解析失败（字符串引号被吞掉）。用编辑器改完请确认
    编码仍是 UTF-8 with BOM。
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Status,
    [switch]$Force,
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'

# 用 $PSScriptRoot 反推仓库根：换机器、换盘符都不需要改脚本
$Root = Split-Path -Parent $PSScriptRoot
$ApiDir = Join-Path $Root 'apps\api'
$PythonExe = Join-Path $ApiDir '.venv\Scripts\python.exe'
$ApiEnvFile = Join-Path $ApiDir '.env'
$TmpDir = Join-Path $Root '.tmp'
$LogDir = Join-Path $Root 'logs'
$PidFile = Join-Path $TmpDir 'backend-pids.json'
$BeatSchedule = Join-Path $TmpDir 'celerybeat-schedule'
# 启动成功要求数据库、Redis 和存储就绪；进程存活单独由 healthz 表达。
$ReadinessUrl = 'http://127.0.0.1:8300/api/v1/readyz'
$ApiPort = 8300

function Get-ServiceDefs {
    # 与指南第 3.1-3.3 节的命令逐字对应：改这里等于改指南，两边要一起改。
    # -P threads 不能省（Windows 没有 fork，默认 prefork 池起不来）；
    # 默认使用一个全队列 worker，减少本地进程和连接池；队列仍按业务分类，便于后续按负载拆分。
    @(
        [pscustomobject]@{
            Name = 'api'
            Desc = '后端 API（uvicorn，8300）'
            Args = @('-m', 'uvicorn', 'tender.api.app:app', '--host', '127.0.0.1', '--port', '8300')
        }
        [pscustomobject]@{
            Name = 'worker'
            Desc = 'Celery 全队列任务执行'
            Args = @(
                '-m', 'celery', '-A', 'tender.worker.celery_app', 'worker',
                '-Q', 'convert,parse,tender,poll,analysis', '-n', 'tender-worker@%h',
                '-P', 'threads', '-c', '7', '-l', 'info'
            )
        }
        [pscustomobject]@{
            Name = 'beat'
            Desc = 'Celery beat（每秒唤醒文档调度）'
            Args = @(
                '-m', 'celery', '-A', 'tender.worker.celery_app', 'beat', '-l', 'info',
                # 给路径加引号：仓库目录将来若含空格，celery 才不会被拆成两个参数
                '--schedule', ([char]34 + $BeatSchedule + [char]34)
            )
        }
    )
}


function Test-ProcessAlive {
    param([int]$ProcessId)
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-BackendServiceName {
    param($ProcessInfo)
    # 可执行文件必须属于当前仓库；只匹配实际模块参数，不能在任意命令文本中搜索关键词。
    if (-not $ProcessInfo -or $ProcessInfo.ExecutablePath -ine $PythonExe) { return $null }
    $prefix = '^(?:"[^"]+"|\S+)\s+-m\s+'
    if ($ProcessInfo.CommandLine -match ($prefix + 'uvicorn\s+tender\.api\.app:app(?:\s|$)')) {
        return 'api'
    }
    if ($ProcessInfo.CommandLine -match ($prefix + 'celery\s+-A\s+tender\.worker\.celery_app\s+(worker|beat)(?:\s|$)')) {
        $serviceKind = $Matches[1]
        if ($serviceKind -eq 'worker' -and $ProcessInfo.CommandLine -match 'tender-(scheduler|poller|analysis)@') {
            return $Matches[1]
        }
        return $serviceKind
    }
    return $null
}

function ConvertTo-ServiceRecord {
    param($ProcessInfo)
    $name = Get-BackendServiceName -ProcessInfo $ProcessInfo
    if (-not $name -or -not $ProcessInfo.CreationDate) { return $null }
    [pscustomobject]@{
        name = $name
        pid = [int]$ProcessInfo.ProcessId
        createdAtUtc = $ProcessInfo.CreationDate.ToUniversalTime().ToString('o')
        commandLine = $ProcessInfo.CommandLine
    }
}

function Test-ServiceIdentity {
    param($Service)
    # PID 会被系统复用；旧格式缺少创建时间时不能据此杀进程，改由严格的现场扫描识别。
    if (-not $Service -or -not $Service.createdAtUtc -or -not $Service.commandLine) { return $false }
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$Service.pid)" -ErrorAction SilentlyContinue
    $identity = ConvertTo-ServiceRecord -ProcessInfo $current
    return $null -ne $identity -and $identity.name -eq $Service.name -and
        $identity.createdAtUtc -eq $Service.createdAtUtc -and
        $identity.commandLine -ceq $Service.commandLine
}

function Stop-ServiceProcess {
    param($Service)
    # 登记记录和现场扫描统一在停止前重新核验，缩短枚举与实际终止之间的时间差。
    if (-not (Test-ServiceIdentity -Service $Service)) { return $false }
    # venv 解释器可能是启动器，核实归属后才连同实际服务子进程一起停止。
    taskkill /F /T /PID $Service.pid 2>&1 | Out-Null
    return $LASTEXITCODE -eq 0
}


function Get-TrackedState {
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    try {
        return Get-Content -LiteralPath $PidFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        # PID 文件损坏时按「没有记录」处理：它是脚本自己写的，不该因此卡住整个流程
        return $null
    }
}


function Write-TrackedState {
    param($Services)
    [pscustomobject]@{
        startedAt = (Get-Date).ToString('s')
        root      = $Root
        # PS 5.1 的坑：@($genericList) 会抛「参数类型不匹配」，必须显式转成普通数组
        services  = [object[]]$Services
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $PidFile -Encoding UTF8
}

function Get-StrayProcesses {
    # 兜底扫描：手工起过、或上次脚本被强杀没留下 PID 的进程。
    # 按当前仓库解释器和完整服务模块识别，避免误伤其它 Python 或 Celery 应用；
    # 已在 PID 文件里登记的不算 stray，否则 -Status 会把脚本刚起的进程也报成未登记。
    $trackedPids = @()
    $state = Get-TrackedState
    if ($state) {
        $trackedPids = @($state.services | Where-Object { Test-ServiceIdentity -Service $_ } | ForEach-Object { [int]$_.pid })
    }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        (Get-BackendServiceName -ProcessInfo $_) -and
        ($trackedPids -notcontains [int]$_.ProcessId)
    }
}


function Show-LogTail {
    param([string]$Name, [int]$Lines = 25)
    $logRole = if ($Name -in @('scheduler', 'poller', 'analysis')) { 'worker' } else { $Name }
    $serviceDir = Join-Path $LogDir $logRole
    if (-not (Test-Path -LiteralPath $serviceDir)) { return }
    $latest = Get-ChildItem -LiteralPath $serviceDir -Filter '*.jsonl' -File |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) {
        Write-Host "[$($latest.Name)] 最后 $Lines 行" -ForegroundColor DarkYellow
        Get-Content -LiteralPath $latest.FullName -Tail $Lines -Encoding UTF8 |
            ForEach-Object { Write-Host "  $_" }
    }
}


function Wait-PortFree {
    param([int]$Port, [int]$Seconds = 15)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
            return $true
        }
        Start-Sleep -Milliseconds 300
    }
    return $false
}


function Wait-ApiReady {
    param([int]$Seconds, [int]$ApiPid)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        # 进程都崩了就没必要等满超时，早点把日志打出来
        if (-not (Test-ProcessAlive -ProcessId $ApiPid)) { return $false }
        try {
            $response = Invoke-WebRequest -Uri $ReadinessUrl -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) { return $true }
        } catch {
            # 端口刚起、还没 accept 时连不上是正常的，继续轮询
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Invoke-BackendStop {
    $stopped = New-Object System.Collections.Generic.List[string]

    $state = Get-TrackedState
    if ($state) {
        foreach ($service in $state.services) {
            if (Stop-ServiceProcess -Service $service) {
                $stopped.Add("$($service.name)(pid=$($service.pid))")
            }
        }
    }

    foreach ($process in Get-StrayProcesses) {
        $service = ConvertTo-ServiceRecord -ProcessInfo $process
        if (Stop-ServiceProcess -Service $service) {
            $stopped.Add("未登记(pid=$($process.ProcessId))")
        }
    }

    if (Test-Path -LiteralPath $PidFile) { Remove-Item -LiteralPath $PidFile -Force }
    return $stopped
}


function Show-BackendStatus {
    $tracked = @{}
    $state = Get-TrackedState
    if ($state) {
        foreach ($service in $state.services) { $tracked[[string]$service.name] = $service }
    }
    $strays = @(Get-StrayProcesses)

    Write-Host ''
    Write-Host '后端进程状态' -ForegroundColor Cyan
    foreach ($def in Get-ServiceDefs) {
        $trackedService = $tracked[$def.Name]
        if (Test-ServiceIdentity -Service $trackedService) {
            Write-Host ("  [运行] {0,-7} pid={1,-6} {2}" -f $def.Name, $trackedService.pid, $def.Desc) -ForegroundColor Green
        } else {
            $untracked = @($strays | Where-Object { (Get-BackendServiceName -ProcessInfo $_) -eq $def.Name })
            if ($untracked.Count -gt 0) {
                Write-Host ("  [运行/未登记] {0} pid={1}" -f $def.Name, ($untracked.ProcessId -join ',')) -ForegroundColor Yellow
            } else {
                Write-Host ("  [停止] {0,-7}          {1}" -f $def.Name, $def.Desc) -ForegroundColor DarkGray
            }
        }
    }

    $listener = Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction SilentlyContinue
    if ($listener) {
        $owners = ($listener.OwningProcess | Sort-Object -Unique) -join ','
        Write-Host "  [端口] $ApiPort 正在监听（pid=$owners）" -ForegroundColor Green
    } else {
        Write-Host "  [端口] $ApiPort 无监听" -ForegroundColor DarkGray
    }

    if ($strays.Count -gt 0) {
        Write-Host ("  [提示] 共 {0} 个现场核实的未登记服务，-Stop 会再次核验后停止" -f $strays.Count) -ForegroundColor Yellow
    }
    Write-Host ''
}

if ($Stop) {
    if ($Status) {
        Write-Host '-Stop 与 -Status 不能同时使用。' -ForegroundColor Red
        exit 1
    }
    $stopped = Invoke-BackendStop
    if ($stopped.Count -eq 0) {
        Write-Host '没有需要停止的后端进程。' -ForegroundColor DarkGray
    } else {
        Write-Host ("已停止 {0} 个进程：{1}" -f $stopped.Count, ($stopped -join '、')) -ForegroundColor Green
    }
    # beat 的 schedule 文件刻意不删：它只记录上次派发时间，删了反而会让下一轮派发提前
    exit 0
}

if ($Status) {
    Show-BackendStatus
    exit 0
}


if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host "找不到后端解释器：$PythonExe" -ForegroundColor Red
    Write-Host '先按《本地启动指南》第 2 节做一次性准备：' -ForegroundColor Yellow
    Write-Host '  Set-Location apps\api' -ForegroundColor Yellow
    Write-Host '  uv sync' -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path -LiteralPath $ApiEnvFile)) {
    Write-Host "找不到配置文件：$ApiEnvFile" -ForegroundColor Red
    Write-Host '先复制模板并填好依赖地址：Copy-Item apps\api\.env.example apps\api\.env' -ForegroundColor Yellow
    exit 1
}


$runningServices = @()
$state = Get-TrackedState
if ($state) {
    foreach ($service in $state.services) {
        if (Test-ServiceIdentity -Service $service) {
            $runningServices += "$($service.name)(pid=$($service.pid))"
        }
    }
}

# 旧 PID 文件不再可信，但现场核实过的服务仍必须参与重复启动与 -Force 判断。
foreach ($process in Get-StrayProcesses) {
    $runningServices += "未登记(pid=$($process.ProcessId))"
}

# 必须先完成日志预检，避免 -Force 停掉旧服务后才发现新实例无法启动。
# 复用后端的解析器：自定义目录与 .env 优先级不能在 PowerShell 再维护一份。
$loggingJson = & $PythonExe -X utf8 -c 'import json; from tender.core.settings import logging_settings; s = logging_settings(); print(json.dumps(dict(directory=str(s.directory), output=s.output)))'
if ($LASTEXITCODE -ne 0) { throw '日志配置无效，请检查 apps/api/.env。' }
$loggingOptions = $loggingJson | ConvertFrom-Json
if ($loggingOptions.output -eq 'stdout') {
    throw '隐藏窗口启动需要 LOG_OUTPUT=file 或 both；stdout 模式请按指南在前台运行。'
}
$LogDir = $loggingOptions.directory
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if ($runningServices.Count -gt 0) {
    if (-not $Force) {
        Write-Host ("后端已在运行：{0}" -f ($runningServices -join '、')) -ForegroundColor Yellow
        Write-Host '重复启动会多出一个 worker 抢同一批队列消息；要重启请加 -Force，或先执行 -Stop。' -ForegroundColor Yellow
        exit 1
    }
    Write-Host ("-Force：先停止在运行的实例 {0}" -f ($runningServices -join '、')) -ForegroundColor DarkGray
    Invoke-BackendStop | Out-Null
    if (-not (Wait-PortFree -Port $ApiPort)) {
        Write-Host "端口 $ApiPort 在停止后仍被占用，请按指南第 5 节手动处理。" -ForegroundColor Red
        exit 1
    }
}

if (Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction SilentlyContinue) {
    $owners = (((Get-NetTCPConnection -State Listen -LocalPort $ApiPort).OwningProcess) | Sort-Object -Unique) -join ','
    Write-Host "端口 $ApiPort 已被 pid=$owners 占用，API 会 bind 失败。处理办法见指南第 5 节。" -ForegroundColor Red
    exit 1
}


# .tmp 被 gitignore，全新工作区没有该目录；PID 记录和 beat 的 schedule 都放在这里。
# 必须在启动进程之前创建，否则写 PID 文件与 beat 初始化 schedule 都会失败。
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

$started = New-Object System.Collections.Generic.List[object]

Write-Host '正在启动后端三个进程……' -ForegroundColor Cyan
foreach ($def in Get-ServiceDefs) {
    # 文件由 Python 日志模块按日期和大小管理；不再生成覆盖历史、无限增长的重定向副本。
    $process = Start-Process -FilePath $PythonExe -ArgumentList $def.Args -WorkingDirectory $ApiDir `
        -WindowStyle Hidden -PassThru

    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)" -ErrorAction SilentlyContinue
    $service = ConvertTo-ServiceRecord -ProcessInfo $processInfo
    if (-not $service) {
        Write-Host "$($def.Name) 已退出或无法核验进程身份，本次启动失败。" -ForegroundColor Red
        Show-LogTail -Name $def.Name
        Write-TrackedState -Services $started
        Invoke-BackendStop | Out-Null
        exit 1
    }
    $started.Add($service)
    Write-Host ("  {0,-7} pid={1}" -f $def.Name, $process.Id) -ForegroundColor Green
    if ($def.Name -eq 'api') {
        # 先等 API 健康再起 worker/beat：反序也能跑，但日志顺序乱，出问题不好定位
        if (-not (Wait-ApiReady -Seconds $TimeoutSeconds -ApiPid $process.Id)) {
            Write-Host ("API 在 {0} 秒内没有就绪，回滚本次启动。" -f $TimeoutSeconds) -ForegroundColor Red
            Show-LogTail -Name 'api'
            Write-TrackedState -Services $started
            Invoke-BackendStop | Out-Null
            exit 1
        }
        Write-Host '  API 就绪检查通过（GET /api/v1/readyz）' -ForegroundColor Green
    } else {
        # 起来后立刻退出说明参数或依赖有问题（漏 -P threads、读不到 .env 等），直接回滚
        Start-Sleep -Seconds 2
        if (-not (Test-ProcessAlive -ProcessId $process.Id)) {
            Write-Host "$($def.Name) 启动后立即退出，回滚本次启动。" -ForegroundColor Red
            Show-LogTail -Name $def.Name
            Write-TrackedState -Services $started
            Invoke-BackendStop | Out-Null
            exit 1
        }
    }
}

Write-TrackedState -Services $started
Write-Host ''
Write-Host '后端已启动' -ForegroundColor Cyan
Write-Host '  API      http://127.0.0.1:8300   （/docs 交互文档；/api/v1/readyz 就绪检查）'
Write-Host '  worker   消费 convert、parse、tender、poll、analysis 队列'
Write-Host '  beat     每秒投递文档调度消息，由 worker 按配置派发差额'
Write-Host ''
Write-Host "日志目录：$LogDir" -ForegroundColor DarkGray
Write-Host '  API / worker / beat 分目录保存 JSONL，默认保留 30 天；查看方法见本地启动指南。' -ForegroundColor DarkGray
Write-Host '  查询状态：  .\scripts\start-backend.ps1 -Status' -ForegroundColor DarkGray
Write-Host '  停止：      .\scripts\start-backend.ps1 -Stop' -ForegroundColor DarkGray
Write-Host ''
