<#
.SYNOPSIS
Prepares one deterministic, real-Kubernetes IncidentPilot failure scenario.

.EXAMPLE
.\scripts\run_kubernetes_scenario.ps1 -Scenario adaptive-resource-pressure -BuildImage
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('restart', 'bad-deployment', 'adaptive-resource-pressure')]
    [string]$Scenario,
    [switch]$BuildImage
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$scenarioRoot = Join-Path $repositoryRoot 'deploy\kubernetes\scenarios'
$baseManifest = Join-Path $scenarioRoot 'base.yaml'
$clearRestartPatch = Join-Path $scenarioRoot 'clear-restart.patch.yaml'
$patchManifest = Join-Path $scenarioRoot "$Scenario.patch.yaml"

function Assert-LastExitCode {
    param([string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

if ($BuildImage) {
    docker build -t incidentpilot-scenarios:local $scenarioRoot
    Assert-LastExitCode 'Building the scenario image'

    if (Get-Command kind -ErrorAction SilentlyContinue) {
        kind load docker-image incidentpilot-scenarios:local --name incidentpilot
        Assert-LastExitCode 'Loading the scenario image into kind'
    }
    else {
        # The desktop app can leave an existing kind cluster available even
        # when kind.exe is not installed on PATH. Import through its Docker
        # control-plane container in that case.
        $node = docker ps --filter 'name=^/incidentpilot-control-plane$' --format '{{.Names}}'
        if (-not $node) {
            throw 'Could not find the incidentpilot kind control-plane container. Install kind or start the cluster first.'
        }

        # Use cmd.exe for the binary tar stream. PowerShell native pipelines
        # can turn that stream into text on Windows.
        cmd.exe /d /c "docker image save incidentpilot-scenarios:local | docker exec -i $node ctr --namespace k8s.io images import -"
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not import incidentpilot-scenarios:local into the kind node.'
        }
    }
}

kubectl apply -f $baseManifest
Assert-LastExitCode 'Applying the scenario base manifest'
# A previous adaptive run may have scaled the Deployment. Reset it explicitly
# so every scenario starts from one replica.
kubectl -n incidentpilot scale deployment/incidentpilot-demo --replicas=1
Assert-LastExitCode 'Resetting the scenario replica count'
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo --timeout=90s
Assert-LastExitCode 'Waiting for the base workload rollout'

# A previous restart leaves this annotation on the pod template. Removing it
# creates the initial transient failure for the restart and adaptive scenarios.
kubectl -n incidentpilot patch deployment incidentpilot-demo --type=strategic `
    --patch-file $clearRestartPatch
Assert-LastExitCode 'Clearing the prior restart marker'
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo --timeout=90s
Assert-LastExitCode 'Waiting for the restart-marker reset rollout'

kubectl -n incidentpilot patch deployment incidentpilot-demo --type=strategic `
    --patch-file $patchManifest
Assert-LastExitCode "Applying the $Scenario scenario patch"
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo --timeout=90s
Assert-LastExitCode "Waiting for the $Scenario scenario rollout"

# Warm the workload endpoint before declaring the scenario ready. Kubernetes
# may report a Pod ready just before its first application-level failure line
# becomes visible through the pod-log API. Without this bounded warm-up, an
# incident started immediately from the dashboard can see only a generic 503
# and safely escalate because no causal evidence is available yet.
$proxyPath = '/api/v1/namespaces/incidentpilot/services/http:incidentpilot-demo:http/proxy/'
$savedErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    1..3 | ForEach-Object {
        kubectl get --raw $proxyPath *> $null
        Start-Sleep -Milliseconds 150
    }
}
finally {
    $ErrorActionPreference = $savedErrorActionPreference
}
Start-Sleep -Seconds 1

kubectl -n incidentpilot get deployments,pods
Write-Host "Scenario '$Scenario' is ready. Start IncidentPilot with ENVIRONMENT=kubernetes and POST /run-incident."
