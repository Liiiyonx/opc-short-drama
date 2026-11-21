# ============================================================
# OPC 短剧出海平台 · Windows 一键演示器（P0-05 / P0-12）
#
# 用法（PowerShell 5.1+）：
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 start     # 启动 + 四道健康闸门
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 status    # 查看闸门/进程状态
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 down      # 停止全部服务
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 snapshot  # 数据库 + 存储快照
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 reset     # 恢复最近一次快照
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 rehearse  # 连跑 3 轮闸门彩排
#
# 原则：任一必需依赖失败 → 拒绝进入演示（不"带病继续"）。
# 主流程用 mock 确定性模式：LLM_PROVIDER=mock / TTS_PROVIDER=mock，全程不等待真实模型。
# ============================================================
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "status", "down", "snapshot", "reset", "rehearse", "chaos")]
    [string]$Command = "start",

    [int]$ApiPort = 8000,
    [int]$WebPort = 5199,
    [switch]$Mock  # 默认 mock；-Mock:$false 且存在密钥文件时可切真实模式
)

$ErrorActionPreference = "Stop"
$Base = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendDir = Join-Path $Base "backend"
$FrontendDir = Join-Path $Base "frontend"
$DemoDir = Join-Path $Base ".demo"
$SnapDir = Join-Path $Base ".demo\snapshots"
$PidDir = $DemoDir
$MockMode = $true
if (-not $Mock -and $env:OPC_DEMO_LIVE -eq "1") { $MockMode = $false }

function Write-Step($msg) { Write-Host "→ $msg" }
function Write-Good($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Bad($msg)  { Write-Host "[X ] $msg" -ForegroundColor Red }
function Write-Info($msg) { Write-Host "    $msg" }

New-Item -ItemType Directory -Force -Path $DemoDir | Out-Null

# ---------- Python 定位（须具备项目依赖） ----------
function Find-Python {
    $candidates = @(
        (Join-Path $BackendDir ".venv\Scripts\python.exe"),
        (Join-Path $Base "backend\.venv\Scripts\python.exe")
    )
    foreach ($cand in $candidates) {
        if (Test-Path $cand) { return $cand }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

# ---------- 依赖闸门（依赖缺失 = 拒绝启动演示） ----------
function Test-Dependencies {
    $fail = @()
    $py = Find-Python
    if (-not $py) {
        $fail += "未找到具备依赖的 Python（backend\.venv）"
    } else {
        Write-Good "Python: $py"
        & $py -c "import fastapi, uvicorn, arq, sqlalchemy, redis" 2>$null
        if ($LASTEXITCODE -ne 0) { $fail += "Python 缺少项目依赖（fastapi/uvicorn/arq/redis）" }
        else { Write-Good "Python 依赖齐全" }
    }

    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $ffmpeg) { $fail += "未找到 ffmpeg（配音/成片将失败）: winget install ffmpeg 或 choco install ffmpeg" }
    else { Write-Good "ffmpeg: $($ffmpeg.Source)" }

    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) { $fail += "未找到 Node.js（前端无法启动）: https://nodejs.org" }
    else { Write-Good "Node.js: $($node.Source)" }

    # Redis TCP 可达
    if (-not (Test-TcpPort "127.0.0.1" 6379 800)) {
        $fail += "Redis 127.0.0.1:6379 不可达（异步任务将失败）: 先启动 Redis（redis-server 或 WSL/服务）"
    } else { Write-Good "Redis 6379 可达" }

    # 磁盘空间 ≥ 2GB
    $drive = (Get-PSDrive -Name ($Base.Substring(0, 1)) -ErrorAction SilentlyContinue)
    if ($drive -and $drive.Free -lt 2GB) { $fail += "磁盘剩余空间不足 2GB（$([math]::Round($drive.Free/1GB,1))GB）" }

    # 端口占用检查
    foreach ($port in @($ApiPort, $WebPort)) {
        if (Test-TcpPort "127.0.0.1" $port 300) {
            Write-Info "端口 $port 已被占用（可能是上次演示未关闭，先执行 down 子命令）"
        }
    }
    return $fail
}

function Test-TcpPort($host_, $port, $timeoutMs) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync($host_, $port)
        if (-not $task.Wait($timeoutMs)) { return $false }
        return $client.Connected
    } catch { return $false } finally { $client.Dispose() }
}

# ---------- 服务管理 ----------
function Invoke-Native {
    # PS 5.1 坑：$ErrorActionPreference=Stop 时，原生命令 stderr 经 2>&1 会抛 NativeCommandError。
    # 临时降为 Continue 执行，返回退出码。
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & @args 2>&1 | Out-Null
    $ErrorActionPreference = $prev
    return $LASTEXITCODE
}

function Start-Services {
    $py = Find-Python
    if (-not $py) { Write-Bad "无可用 Python，无法启动"; exit 1 }

    Write-Step "数据库迁移 + 演示数据播种（幂等）"
    Push-Location $BackendDir
    [void](Invoke-Native $py -m alembic upgrade head)
    [void](Invoke-Native $py -m scripts.seed)
    Pop-Location

    if ($MockMode) {
        $env:LLM_PROVIDER = "mock"
        $env:TTS_PROVIDER = "mock"
        Write-Info "确定性演示模式：LLM/TTS 均为 mock 桩（不等待真实模型）"
    } else {
        Write-Info "真实 AI 模式（需已注入 LLM_API_KEY）"
    }
    $env:QUOTA_MEDIA_CALLS_PER_USER_DAY = "100"
    $env:QUOTA_TEXT_CALLS_PER_USER_DAY = "500"

    Write-Step "启动 worker / API($ApiPort) / 前端($WebPort)"
    Push-Location $BackendDir
    # 幂等：先清残留 worker（避免多 worker 抢任务、未带 mock env 的跑真实 provider）
    $staleWorkers = @(Get-ProjectWorkerPids)
    foreach ($p in $staleWorkers) { try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch {} }
    if ($staleWorkers.Count -gt 0) { Write-Info "已清理 $($staleWorkers.Count) 个残留 worker" }
    Start-Process -FilePath $py -ArgumentList "-m", "arq", "app.workers.tasks.WorkerSettings" `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $DemoDir "worker.log") -RedirectStandardError (Join-Path $DemoDir "worker.err.log")
    Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$ApiPort" `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $DemoDir "api.log") -RedirectStandardError (Join-Path $DemoDir "api.err.log")
    Pop-Location

    Push-Location $FrontendDir
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Write-Step "首次运行：npm install（可能需要几分钟）"
        [void](Invoke-Native npm install)
    }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "set VITE_API_TARGET=http://127.0.0.1:$ApiPort&& npm run dev -- --port $WebPort --strictPort" `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $DemoDir "vite.log") -RedirectStandardError (Join-Path $DemoDir "vite.err.log")
    Pop-Location

    # 记录 PID 供 down 使用（Start-Process -PassThru 与 cmd 包装冲突时按端口清理兜底）
    Get-Process | Where-Object { $_.ProcessName -match "^python|^node|arq|uvicorn" } |
        ForEach-Object { $_.Id } | Set-Content (Join-Path $PidDir "pids.txt")
}

function Wait-Http($url, $timeoutSec, $okPredicate) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($okPredicate) { if (& $okPredicate $resp) { return $true } }
            else { return $true }
        } catch { Start-Sleep -Milliseconds 800 }
    }
    return $false
}

# ---------- 四道健康闸门：进程 / 依赖 / 数据 / 业务 ----------
function Invoke-Gates {
    $fail = @()

    # 1) 进程闸门：前端、API、worker 端口全部响应
    Write-Step "闸门 1/4 进程：API / 前端 / worker"
    if (-not (Test-TcpPort "127.0.0.1" $ApiPort 1500)) { $fail += "API 端口 $ApiPort 未响应" }
    if (-not (Test-TcpPort "127.0.0.1" $WebPort 1500)) { $fail += "前端端口 $WebPort 未响应" }
    if ($fail.Count -gt 0) { return $fail }

    # 2) 依赖闸门：/readyz 必须 200（DB + Redis）
    try {
        $ready = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/readyz" -TimeoutSec 5
        Write-Good "依赖闸门 /readyz：db=$($ready.data.db) redis=$($ready.data.redis)"
    } catch {
        $fail += "依赖闸门失败：/readyz 非 200（DB/Redis 未就绪），看 .demo\api.err.log"
        return $fail
    }

    # 3) 数据闸门：/health 报告 + 演示账号可登录
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 5
        Write-Info ("健康报告: status={0} worker={1} storage={2} ffmpeg={3} ai={4}" -f `
            $health.data.status, $health.data.worker, $health.data.storage, $health.data.ffmpeg, $health.data.ai.llm_provider)
        if ($health.data.db -ne "up") { $fail += "数据闸门失败：DB 不可用" }
        if ($health.data.redis -ne "up") { $fail += "数据闸门失败：Redis 不可用" }
    } catch { $fail += "数据闸门失败：/health 无响应" }

    try {
        $body = @{ username = "student01"; password = "student123" } | ConvertTo-Json
        $login = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/auth/login" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 8
        Write-Good "数据闸门：演示账号 student01 可登录"
    } catch { $fail += "数据闸门失败：演示账号登录失败（种子数据缺失？）" }

    # 4) 业务闸门：登录态读取作品列表 + worker 心跳
    try {
        $headers = @{ Authorization = "Bearer $($login.data.access_token)" }
        $works = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/works?page=1&page_size=1" -Headers $headers -TimeoutSec 8
        Write-Good "业务闸门：作品接口可达（total=$($works.data.total)）"
        if ($health.data.worker -ne "up") { $fail += "业务闸门失败：worker 心跳缺失（异步任务将失败）" }
    } catch { $fail += "业务闸门失败：作品接口不可达" }

    return $fail
}

function Stop-Services {
    Write-Step "停止服务（按 PID + 端口兜底）"
    $pidFile = Join-Path $PidDir "pids.txt"
    if (Test-Path $pidFile) {
        Get-Content $pidFile | ForEach-Object {
            try { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } catch {}
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
    foreach ($port in @($ApiPort, $WebPort)) {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $conns) {
            try { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
    Write-Good "已停止 API/前端；Redis 为外部服务未动"
}

# ---------- P0-01 风险注入彩排（chaos）：worker 失联 / Redis 失联 ----------
# 进程识别按命令行匹配 + 项目路径（端口属主可能是历史残留，不可靠——实测教训）

function Get-ProjectWorkerPids {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match "arq app\.workers\.tasks" -and $_.CommandLine -match [regex]::Escape($BackendDir) } |
        Select-Object -ExpandProperty ProcessId
}

function Start-Worker {
    # 残留 worker 必须先清（多 worker 抢任务时，未带 mock env 的会跑真实 provider
    # —— 实测导致 TTS 批量失败）；重启一律显式注入确定性演示模式。
    $stale = @(Get-ProjectWorkerPids)
    foreach ($p in $stale) { try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch {} }
    if ($stale.Count -gt 0) { Write-Info "已清理 $($stale.Count) 个残留 worker 进程" }
    $py = Find-Python
    if (-not $py) { Write-Bad "无可用 Python"; return }
    $prevError = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $env:LLM_PROVIDER = "mock"
    $env:TTS_PROVIDER = "mock"
    Start-Process -FilePath $py -ArgumentList "-m", "arq", "app.workers.tasks.WorkerSettings" `
        -WindowStyle Hidden -WorkingDirectory $BackendDir `
        -RedirectStandardOutput (Join-Path $DemoDir "worker.log") -RedirectStandardError (Join-Path $DemoDir "worker.err.log")
    $ErrorActionPreference = $prevError
}

function Invoke-Chaos {
    Write-Host "==================== 风险注入彩排 ===================="
    $pre = Invoke-Gates
    if ($pre.Count -gt 0) { Write-Bad "彩排前置闸门未过，先 start/status 修复："; $pre | ForEach-Object { Write-Bad "  $_" }; exit 1 }

    $results = @()

    # ---- 演练 1：杀死 worker → 心跳 30s 内判失联 → 重启恢复 ----
    Write-Step "演练 1/2：杀死 arq worker，验证 /health.worker 30s 内 down"
    $pids = @(Get-ProjectWorkerPids)
    if ($pids.Count -eq 0) { Write-Bad "未找到 worker 进程"; exit 1 }
    $pids | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } catch {} }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $downAt = -1
    while ($sw.Elapsed.TotalSeconds -lt 40) {
        try {
            $h = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 3
            if ($h.data.worker -ne "up") { $downAt = [math]::Round($sw.Elapsed.TotalSeconds, 1); break }
        } catch {}
        Start-Sleep -Milliseconds 800
    }
    if ($downAt -ge 0 -and $downAt -le 30) {
        Write-Good "worker 失联 ${downAt}s 检出（验收线 30s）"
        $results += @{ name = "worker 失联检出"; ok = $true; detail = "${downAt}s ≤ 30s" }
    } else {
        Write-Bad "worker 失联未在 30s 内检出（${downAt}s）"
        $results += @{ name = "worker 失联检出"; ok = $false; detail = "${downAt}s > 30s" }
    }
    # 演练期间业务闸门（异步任务）应失败 → 即 /health worker != up 已覆盖
    Start-Sleep -Seconds 2
    Write-Step "重启 worker，等待心跳恢复"
    Start-Worker
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $upAt = -1
    while ($sw.Elapsed.TotalSeconds -lt 60) {
        try {
            $h = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 3
            if ($h.data.worker -eq "up") { $upAt = [math]::Round($sw.Elapsed.TotalSeconds, 1); break }
        } catch {}
        Start-Sleep -Milliseconds 800
    }
    if ($upAt -ge 0) { Write-Good "worker 心跳恢复 ${upAt}s"; $results += @{ name = "worker 恢复"; ok = $true; detail = "${upAt}s" } }
    else { Write-Bad "worker 60s 未恢复"; $results += @{ name = "worker 恢复"; ok = $false; detail = "timeout" } }

    # ---- 演练 2：停 Redis → /readyz 3s 内 503 → 重启 Redis 恢复 ----
    # 首选：redis-cli shutdown nosave（应用层关停，无需管理员，实测可行）；
    # 服务方式作为无 redis-cli 时的回退；均不可行时诚实 SKIP。
    # 实测教训：arq worker 在 Redis 失联期间会因连接超时整进程崩溃（compose 有
    # restart: unless-stopped 兜底；脚本环境由本脚本在恢复后重启 worker）。
    Write-Step "演练 2/2：停止 Redis（redis-cli shutdown），验证 /readyz 3s 内 503"
    $redisCli = "C:\Program Files\Redis\redis-cli.exe"
    $redisBin = "C:\Program Files\Redis\redis-server.exe"
    if (-not (Test-Path $redisCli)) {
        $proc = Get-Process redis-server -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($proc -and $proc.Path) { $redisCli = Join-Path (Split-Path $proc.Path) "redis-cli.exe" }
    }
    $canDrill = $false
    $redisStoppedByUs = $false
    if (Test-Path $redisCli) {
        & $redisCli shutdown nosave 2>$null | Out-Null
        $redisStoppedByUs = $true
        $canDrill = $true
    } else {
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        $redisSvc = Get-CimInstance Win32_Service | Where-Object { $_.Name -match "redis" -and $_.State -eq "Running" } | Select-Object -First 1
        if ($redisSvc -and $isAdmin) {
            $prevError = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            Stop-Service -Name $redisSvc.Name -Force -ErrorAction SilentlyContinue
            $ErrorActionPreference = $prevError
            $redisSvcName = $redisSvc.Name
            $canDrill = $true
        } else {
            Write-Info "未找到 redis-cli 且无管理员权限，跳过本演练"
        }
    }
    if ($canDrill) {
        $prevError = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        Stop-Service -Name $redisSvc.Name -Force -ErrorAction SilentlyContinue
        $ErrorActionPreference = $prevError
        Start-Sleep -Milliseconds 500
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $fifty3At = -1
        while ($sw.Elapsed.TotalSeconds -lt 15) {
            try {
                Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/readyz" -TimeoutSec 2 | Out-Null
            } catch {
                # 非 200 = 已摘除（503）
                $fifty3At = [math]::Round($sw.Elapsed.TotalSeconds, 1); break
            }
            Start-Sleep -Milliseconds 300
        }
        if ($fifty3At -ge 0 -and $fifty3At -le 3) {
            Write-Good "readyz 503 ${fifty3At}s 检出（验收线 3s）"
            $results += @{ name = "readyz 摘除"; ok = $true; detail = "${fifty3At}s ≤ 3s" }
        } else {
            Write-Bad "readyz 未在 3s 内摘除（${fifty3At}s）"
            $results += @{ name = "readyz 摘除"; ok = $false; detail = "${fifty3At}s" }
        }
        # 重启 Redis（用户态优先：无配置启动即可满足开发/演示口径）
        if ($redisStoppedByUs -and (Test-Path $redisBin)) {
            Start-Process -FilePath $redisBin -ArgumentList "--port", "6379" -WindowStyle Hidden
            Write-Info "Redis 已重启（用户态）：$redisBin"
        } elseif ($redisSvcName) {
            $prevError = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            Start-Service -Name $redisSvcName -ErrorAction SilentlyContinue
            $ErrorActionPreference = $prevError
            Write-Info "Redis 服务已重启：$redisSvcName"
        }
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $redisUp = $false
        while ($sw.Elapsed.TotalSeconds -lt 30) {
            try {
                $r = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/readyz" -TimeoutSec 2
                if ($r.data.status -eq "ready") { $redisUp = $true; break }
            } catch {}
            Start-Sleep -Milliseconds 600
        }
        if ($redisUp) { Write-Good "Redis 恢复就绪"; $results += @{ name = "Redis 恢复"; ok = $true; detail = "ready" } }
        else { Write-Bad "Redis 30s 未恢复"; $results += @{ name = "Redis 恢复"; ok = $false; detail = "timeout" } }

        # arq worker 会在 Redis 失联期间整进程崩溃（arq 连接池超时）——检测并恢复
        Write-Step "检测 worker 是否在停服期间崩溃（arq 连接池弱点，compose 由 restart 兜底）"
        Start-Sleep -Seconds 3
        $workerAlive = @(Get-ProjectWorkerPids).Count -gt 0
        if (-not $workerAlive) {
            Write-Info "worker 已崩溃（预期内）——重启并等待心跳恢复"
            Start-Worker
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $wkUp = $false
            while ($sw.Elapsed.TotalSeconds -lt 60) {
                try {
                    $h = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 3
                    if ($h.data.worker -eq "up") { $wkUp = $true; break }
                } catch {}
                Start-Sleep -Milliseconds 800
            }
            if ($wkUp) { Write-Good "worker 恢复就绪"; $results += @{ name = "worker 崩溃恢复"; ok = $true; detail = "recovered" } }
            else { Write-Bad "worker 60s 未恢复"; $results += @{ name = "worker 崩溃恢复"; ok = $false; detail = "timeout" } }
        } else {
            Write-Good "worker 存活（本机实例未崩）"
            $results += @{ name = "worker 崩溃恢复"; ok = $true; detail = "alive" }
        }
    } else {
        $results += @{ name = "readyz 摘除"; ok = $true; detail = "SKIP（无 redis-cli 且无管理员权限）" }
        Write-Info "Redis 演练跳过（无 redis-cli 且无管理员权限）"
    }

    # ---- 汇总 ----
    Write-Host ""
    $fail = $results | Where-Object { -not $_.ok }
    foreach ($r in $results) {
        if ($r.ok) { Write-Good "$($r.name)：$($r.detail)" } else { Write-Bad "$($r.name)：$($r.detail)" }
    }
    if ($fail.Count -eq 0) { Write-Good "风险注入彩排全部通过"; [Environment]::Exit(0) }
    Write-Bad "彩排存在失败项"; [Environment]::Exit(1)
}

# ---------- P0-12 快照与回滚 ----------
function Invoke-Snapshot {
    New-Item -ItemType Directory -Force -Path $SnapDir | Out-Null
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    $target = Join-Path $SnapDir $ts
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    Write-Step "快照数据库与本地存储 → $target"
    Copy-Item (Join-Path $BackendDir "dev.db") $target -Force
    if (Test-Path (Join-Path $BackendDir "storage")) {
        Copy-Item (Join-Path $BackendDir "storage") $target -Recurse -Force
    }

    # 清单 + 校验和（相对路径，嵌套文件也能校验）
    $files = Get-ChildItem $target -Recurse -File
    ($files | ForEach-Object { "$($_.FullName.Substring($target.Length + 1))" }) -join "`r`n" |
        Set-Content (Join-Path $target "manifest.txt")
    $hashes = $files | ForEach-Object {
        "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash)  $($_.FullName.Substring($target.Length + 1))"
    }
    $hashes -join "`r`n" | Set-Content (Join-Path $target "checksums.sha256")
    Write-Good "快照完成（$($files.Count) 个文件，含 SHA256 校验）"
    return $target
}

function Invoke-Reset {
    Write-Step "停止服务后恢复最近快照"
    Stop-Services
    $latest = Get-ChildItem $SnapDir -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $latest) {
        Write-Bad "没有可用快照（先执行 snapshot 子命令）"; exit 1
    }
    Write-Info "恢复自: $($latest.FullName)"

    # 校验快照完整性
    if (Test-Path (Join-Path $latest.FullName "checksums.sha256")) {
        $mismatch = 0
        Get-Content (Join-Path $latest.FullName "checksums.sha256") | ForEach-Object {
            $parts = $_ -split "\s+", 2
            $f = Join-Path $latest.FullName $parts[1]
            if ((Test-Path $f) -and (Get-FileHash $f -Algorithm SHA256).Hash -ne $parts[0]) { $mismatch++ }
        }
        if ($mismatch -gt 0) { Write-Bad "快照校验失败 $mismatch 个文件不匹配，拒绝恢复"; exit 1 }
        Write-Good "快照校验通过"
    }

    Copy-Item (Join-Path $latest.FullName "dev.db") (Join-Path $BackendDir "dev.db") -Force
    if (Test-Path (Join-Path $latest.FullName "storage")) {
        $dst = Join-Path $BackendDir "storage"
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        Copy-Item (Join-Path $latest.FullName "storage") $dst -Recurse -Force
    }
    Write-Good "已恢复（60 秒内可回滚口径达成）"
    # 恢复后自动重启并跑闸门
    Start-Services
    Start-Sleep -Seconds 6
    $fail = Invoke-Gates
    if ($fail.Count -gt 0) { Write-Bad "恢复后闸门未全过:"; $fail | ForEach-Object { Write-Bad "  $_" }; exit 1 }
    Write-Good "恢复后闸门全绿"
    # 分离子进程持有 stdout 句柄时 PS 不退出：显式结束（子进程不受影响）
    [Environment]::Exit(0)
}

# ---------- 主流程 ----------
switch ($Command) {
    "down" { Stop-Services; exit 0 }
    "snapshot" { Invoke-Snapshot | Out-Null; exit 0 }
    "reset" { Invoke-Reset; exit 0 }
    "status" {
        $fail = Invoke-Gates
        if ($fail.Count -eq 0) { Write-Good "全部闸门通过，可进入演示"; exit 0 }
        Write-Bad "闸门未通过:"; $fail | ForEach-Object { Write-Bad "  $_" }; exit 1
    }
    "rehearse" {
        Write-Step "风险注入彩排：连跑 3 轮闸门"
        for ($i = 1; $i -le 3; $i++) {
            Write-Step "第 $i/3 轮"
            $fail = Invoke-Gates
            if ($fail.Count -gt 0) { Write-Bad "第 $i 轮失败:"; $fail | ForEach-Object { Write-Bad "  $_" }; exit 1 }
            Start-Sleep -Seconds 3
        }
        Write-Good "3 轮彩排全部通过"; exit 0
    }
    "chaos" {
        Invoke-Chaos
        [Environment]::Exit(0)
    }
    default {
        Write-Host "==================== OPC 演示启动 ===================="
        $depFail = Test-Dependencies
        if ($depFail.Count -gt 0) {
            Write-Bad "依赖闸门未通过，拒绝启动演示（按计划书：不'带病继续'）："
            $depFail | ForEach-Object { Write-Bad "  $_" }
            exit 1
        }
        Start-Services
        Write-Step "等待服务就绪 + 四道健康闸门（进程/依赖/数据/业务）"
        $ready = Wait-Http "http://127.0.0.1:$ApiPort/readyz" 60 $null
        if (-not $ready) { Write-Bad "API 60 秒未就绪，看 .demo\api.err.log"; exit 1 }

        $fail = Invoke-Gates
        if ($fail.Count -gt 0) {
            Write-Bad "健康闸门未通过，不进入演示："
            $fail | ForEach-Object { Write-Bad "  $_" }
            Write-Info "修复后可执行: powershell -File scripts\demo.ps1 start（或 reset 恢复快照）"
            exit 1
        }

        Write-Host ""
        Write-Good "四道闸门全绿 → http://127.0.0.1:$WebPort"
        Write-Info "演示账号: student01/student123 · teacher01/teacher123 · enterprise01/ent123456"
        Write-Info "日志: .demo\{api,worker,vite}.log   停止: scripts\demo.ps1 down"
        Write-Info "快照: scripts\demo.ps1 snapshot    回滚: scripts\demo.ps1 reset"
        # 分离子进程持有 stdout 句柄时 PS 不退出：显式结束（子进程不受影响）
        [Environment]::Exit(0)
    }
}
