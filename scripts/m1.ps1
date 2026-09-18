param([ValidateSet('Up','Stop','Status','Verify')][string]$Action='Up', [switch]$Setup, [switch]$InstallOnly,
      [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,40}$')][string]$ProjectName='citeweave-m0')
$ErrorActionPreference='Stop'
$cwRoot = Split-Path -Parent $PSScriptRoot
if ($InstallOnly -and -not $Setup) { throw 'InstallOnly requires Setup.' }
Set-Location -LiteralPath $cwRoot
function Invoke-Cw([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Exe (exit $LASTEXITCODE)" }
}
$cwPython = Join-Path $cwRoot '.venv/Scripts/python.exe'
$cwCompose = @('compose','-p',$ProjectName,'--env-file','.env','-f','deploy/compose.m0.yml','-f','deploy/compose.m1.yml')
if ($Setup) {
    if (-not (Test-Path -LiteralPath $cwPython)) { Invoke-Cw 'python' @('-m','venv','.venv') }
    Invoke-Cw $cwPython @('-m','pip','install','uv')
    Invoke-Cw (Join-Path $cwRoot '.venv/Scripts/uv.exe') @('sync','--frozen')
    if (-not (Test-Path -LiteralPath '.runtime/ml/Scripts/python.exe')) { Invoke-Cw 'python' @('-m','venv','.runtime/ml') }
    # The complete flat lock is installed from explicit registries. Only torch comes from
    # the CUDA wheel index; generic packages must not be shadowed by that index.
    $cwModelLock = Get-Content -LiteralPath 'requirements-models.lock'
    $cwTorchLock = @($cwModelLock | Where-Object { $_ -match '^torch==' })
    if ($cwTorchLock.Count -ne 1) { throw 'Expected exactly one pinned torch wheel.' }
    $cwTorchLock | Set-Content -LiteralPath '.runtime/models-torch.lock' -Encoding utf8
    $cwModelLock | Where-Object { $_ -notmatch '^torch==' } | Set-Content -LiteralPath '.runtime/models-pypi.lock' -Encoding utf8
    Invoke-Cw (Join-Path $cwRoot '.venv/Scripts/uv.exe') @('pip','install','--python','.runtime/ml/Scripts/python.exe','--no-deps','-r','.runtime/models-pypi.lock','--index-url','https://pypi.org/simple')
    Invoke-Cw (Join-Path $cwRoot '.venv/Scripts/uv.exe') @('pip','install','--python','.runtime/ml/Scripts/python.exe','--no-deps','-r','.runtime/models-torch.lock','--index-url','https://download.pytorch.org/whl/cu126')
    Invoke-Cw (Join-Path $cwRoot '.venv/Scripts/uv.exe') @('pip','check','--python','.runtime/ml/Scripts/python.exe')
    Invoke-Cw '.runtime/ml/Scripts/python.exe' @('experiments/model_download.py')
    Push-Location 'apps/web'
    try { Invoke-Cw 'pnpm' @('install','--frozen-lockfile') } finally { Pop-Location }
    if ($InstallOnly) { Write-Output 'Locked dependencies and public model revisions installed; services not started.'; exit }
}
if (-not (Test-Path -LiteralPath $cwPython)) { throw 'Run .\scripts\m1.ps1 -Setup first (Python 3.12 / Node / pnpm / Docker required).' }
if ($Action -eq 'Verify') { Invoke-Cw $cwPython @('scripts/verify.py'); exit }
if ($Action -eq 'Status') {
    Invoke-Cw 'docker' ($cwCompose + @('ps'))
    try { Invoke-RestMethod 'http://127.0.0.1:18081/health' -TimeoutSec 3 } catch { Write-Output 'Model gateway offline' }
    exit
}
if ($Action -eq 'Stop') {
    Invoke-Cw 'docker' ($cwCompose + @('stop','api','m1-worker','postgres','broker','qdrant'))
    # Stop only our gateway after checking its command line; never stop all Python processes.
    $cwProcesses = Get-CimInstance Win32_Process -Filter "name='python.exe'"
    $cwOwned = @($cwProcesses | Where-Object { ([string]$_.CommandLine).Replace('\','/') -like '*scripts/model_gateway.py*' -and ([string]$_.CommandLine).Replace('\','/') -like ('*'+$cwRoot.Replace('\','/')+'*') })
    $cwParentIds = @($cwOwned.ProcessId)
    $cwOwned += @($cwProcesses | Where-Object { $_.ParentProcessId -in $cwParentIds -and ([string]$_.CommandLine).Replace('\','/') -like '*scripts/model_gateway.py*' })
    foreach ($cwProcess in $cwOwned | Sort-Object ProcessId -Unique) {
        if (([string]$cwProcess.CommandLine).Replace('\','/') -like '*scripts/model_gateway.py*') {
            Stop-Process -Id $cwProcess.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    exit
}
Invoke-Cw $cwPython @('experiments/bootstrap.py')
Invoke-Cw 'docker' @('info','--format','{{.ServerVersion}}')
Invoke-Cw $cwPython @('scripts/prepare_web.py')
Push-Location 'apps/web'
try {
    Invoke-Cw 'node' @('node_modules/typescript/bin/tsc','--noEmit')
    Invoke-Cw 'node' @('node_modules/vite/bin/vite.js','build')
} finally { Pop-Location }
$cwModelHealthy = $false
try { $cwModelHealthy = (Invoke-RestMethod 'http://127.0.0.1:18081/health' -TimeoutSec 2).status -eq 'ready' } catch { $cwModelHealthy = $false }
if (-not $cwModelHealthy) {
    New-Item -ItemType Directory -Force -Path '.runtime/logs','.runtime/faults','.runtime/blobs' | Out-Null
    $cwGateway = Join-Path $cwRoot 'scripts/model_gateway.py'
    $cwChild = Start-Process -FilePath (Join-Path $cwRoot '.runtime/ml/Scripts/python.exe') -ArgumentList @('-u',('"'+$cwGateway+'"')) -WorkingDirectory $cwRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput '.runtime/logs/model.out.log' -RedirectStandardError '.runtime/logs/model.err.log'
    $cwChild.Id | Set-Content '.runtime/model.pid'
    $cwDeadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $cwDeadline -and -not $cwModelHealthy) {
        if ($cwChild.HasExited) { throw 'Model gateway exited; see .runtime/logs/model.err.log' }
        try { $cwModelHealthy = (Invoke-RestMethod 'http://127.0.0.1:18081/health' -TimeoutSec 2).status -eq 'ready' } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $cwModelHealthy) { throw 'Model startup deadline exceeded; inspect local log before retrying.' }
}
Invoke-Cw 'docker' ($cwCompose + @('build','api'))
Invoke-Cw 'docker' ($cwCompose + @('up','-d','postgres','broker','qdrant','api','m1-worker'))
Invoke-Cw 'docker' @('exec',($ProjectName+'-m1-worker-1'),'python','-c',"import urllib.request; urllib.request.urlopen('http://host.docker.internal:18081/health',timeout=3); print('Gateway reachable from worker')")
Write-Output 'CiteWeave ready: http://127.0.0.1:18080/ (login token is CW_ADMIN_TOKEN in your local .env)'
