[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$scenarioRoot = Join-Path $repositoryRoot 'deploy\kubernetes\scenarios'

kubectl cluster-info *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'The current Kubernetes cluster is unreachable. Run scripts\check-k8s-demo.ps1.'
}

kubectl apply -f (Join-Path $scenarioRoot 'base.yaml')
if ($LASTEXITCODE -ne 0) { throw 'Could not apply the baseline workload.' }
kubectl -n incidentpilot scale deployment/incidentpilot-demo --replicas=1
if ($LASTEXITCODE -ne 0) { throw 'Could not reset replicas to one.' }
kubectl -n incidentpilot patch deployment incidentpilot-demo --type=strategic --patch-file (Join-Path $scenarioRoot 'clear-restart.patch.yaml')
if ($LASTEXITCODE -ne 0) { throw 'Could not clear the restart marker.' }
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo --timeout=90s
if ($LASTEXITCODE -ne 0) { throw 'The baseline workload did not become ready.' }

Write-Host 'Kubernetes demo reset to healthy v41 with one replica.' -ForegroundColor Green
