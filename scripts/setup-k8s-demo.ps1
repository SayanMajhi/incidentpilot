[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$clusterConfig = Join-Path $repositoryRoot 'deploy\kubernetes\kind-cluster.yaml'
$namespaceManifest = Join-Path $repositoryRoot 'deploy\kubernetes\namespace.yaml'
$rbacManifest = Join-Path $repositoryRoot 'deploy\kubernetes\rbac.yaml'
$scenarioRoot = Join-Path $repositoryRoot 'deploy\kubernetes\scenarios'
$baseManifest = Join-Path $scenarioRoot 'base.yaml'

function Require-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is missing. $InstallHint"
    }
}

function Assert-ExitCode {
    param([string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

Require-Command 'docker' 'Install Docker Desktop and start it.'
Require-Command 'kubectl' 'Run: winget install Kubernetes.kubectl'
Require-Command 'kind' 'Run: winget install Kubernetes.kind'

docker info *> $null
Assert-ExitCode 'Connecting to Docker'

$clusters = @(kind get clusters 2>$null)
if ($clusters -notcontains 'incidentpilot') {
    Write-Host 'Creating kind cluster incidentpilot...'
    kind create cluster --config $clusterConfig
    Assert-ExitCode 'Creating the kind cluster'
}
else {
    kubectl config use-context kind-incidentpilot *> $null
    Assert-ExitCode 'Selecting kind-incidentpilot'
    kubectl cluster-info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'The incidentpilot cluster exists but is unreachable. Start Docker Desktop, then run this script again.'
    }
}

kubectl apply -f $namespaceManifest
Assert-ExitCode 'Applying the namespace'
kubectl apply -f $rbacManifest
Assert-ExitCode 'Applying namespace-scoped RBAC'

docker build -t incidentpilot-scenarios:local $scenarioRoot
Assert-ExitCode 'Building the deterministic scenario image'
kind load docker-image incidentpilot-scenarios:local --name incidentpilot
Assert-ExitCode 'Loading the image into kind'

kubectl apply -f $baseManifest
Assert-ExitCode 'Applying the scenario workload and services'
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo --timeout=90s
Assert-ExitCode 'Waiting for the demo workload'

Write-Host 'Kubernetes demo setup complete.' -ForegroundColor Green
Write-Host 'Next: .\scripts\run-k8s-demo.ps1'
