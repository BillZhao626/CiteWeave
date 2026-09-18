param([ValidateSet('e5-small','bge-m3')][string]$Embedding='e5-small')
$ErrorActionPreference='Stop'
$cwRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $cwRoot
# This local experiment is a maintenance operation. Refuse to interrupt durable work.
& '.venv/Scripts/python.exe' -c 'from sqlalchemy import select; from citeweave.db import transaction; from citeweave.domain import EvalRunRow,QueryRunRow; from citeweave.lifecycle import LIVE; from citeweave.domain import IngestionJobRow; exec("with transaction() as db:\n assert not db.scalar(select(EvalRunRow.id).where(EvalRunRow.status.in_([\"PENDING\",\"RUNNING\"])).limit(1)), \"evaluation_active\"\n assert not db.scalar(select(QueryRunRow.id).where(QueryRunRow.status == \"RUNNING\").limit(1)), \"query_active\"\n assert not db.scalar(select(IngestionJobRow.id).where(IngestionJobRow.status.in_(LIVE)).limit(1)), \"ingestion_active\"")'
if ($LASTEXITCODE -ne 0) { throw 'Cannot switch gateway while work is active.' }
$cwProcesses = Get-CimInstance Win32_Process -Filter "name='python.exe'"
$cwOwned = @($cwProcesses | Where-Object { ([string]$_.CommandLine).Replace('\','/') -like '*scripts/model_gateway.py*' -and ([string]$_.CommandLine).Replace('\','/') -like ('*'+$cwRoot.Replace('\','/')+'*') })
$cwParentIds = @($cwOwned.ProcessId)
$cwOwned += @($cwProcesses | Where-Object { $_.ParentProcessId -in $cwParentIds -and ([string]$_.CommandLine).Replace('\','/') -like '*scripts/model_gateway.py*' })
foreach ($cwProcess in $cwOwned | Sort-Object ProcessId -Unique) { Stop-Process -Id $cwProcess.ProcessId -Force -ErrorAction SilentlyContinue }
$cwScript = Join-Path $cwRoot 'scripts/model_gateway.py'
$cwChild = Start-Process -FilePath (Join-Path $cwRoot '.runtime/ml/Scripts/python.exe') -ArgumentList @('-u',('"'+$cwScript+'"'),'--embedding',$Embedding) -WorkingDirectory $cwRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput ('.runtime/logs/revisit-model-'+$Embedding+'.out.log') -RedirectStandardError ('.runtime/logs/revisit-model-'+$Embedding+'.err.log')
$cwChild.Id | Set-Content '.runtime/model.pid'
$cwDeadline = (Get-Date).AddSeconds(240)
while ((Get-Date) -lt $cwDeadline) {
    if ($cwChild.HasExited) { throw 'Gateway exited; inspect local experiment logs.' }
    try {
        $cwHealth = Invoke-RestMethod 'http://127.0.0.1:18081/health' -TimeoutSec 2
        $cwExpected = if ($Embedding -eq 'bge-m3') { 'BAAI/bge-m3' } else { 'intfloat/multilingual-e5-small' }
        if ($cwHealth.status -eq 'ready' -and $cwHealth.embedding.model -eq $cwExpected) { $cwHealth | ConvertTo-Json -Depth 6; exit }
    } catch { }
    Start-Sleep -Milliseconds 500
}
throw 'Gateway startup deadline exceeded; no automatic repeated launches.'
