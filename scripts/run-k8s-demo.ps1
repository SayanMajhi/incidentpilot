[CmdletBinding()]
param(
    [ValidateSet('restart', 'bad-deployment', 'adaptive-resource-pressure')]
    [string]$Scenario = 'adaptive-resource-pressure',
    [switch]$ScenarioOnly
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$scenarioScript = Join-Path $PSScriptRoot 'run_kubernetes_scenario.ps1'
$agentScript = Join-Path $PSScriptRoot 'run_kubernetes_agent.py'

& (Join-Path $PSScriptRoot 'check-k8s-demo.ps1')
if ($LASTEXITCODE -ne 0) {
    throw 'Kubernetes prerequisites are not ready. Run scripts\setup-k8s-demo.ps1 first.'
}

& $scenarioScript -Scenario $Scenario
if ($ScenarioOnly) {
    Write-Host 'Scenario is active. Run the backend and click Run Incident in the dashboard.'
    exit 0
}

$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw 'Python was not found. Create .venv and install requirements.txt plus requirements-kubernetes.txt.'
    }
    $python = $pythonCommand.Source
}

$previousEnvironment = $env:ENVIRONMENT
$previousLlm = $env:LLM_ENABLED
try {
    $env:ENVIRONMENT = 'kubernetes'
    $env:LLM_ENABLED = 'false'
    & $python $agentScript
    if ($LASTEXITCODE -ne 0) {
        throw 'The IncidentPilot Kubernetes run failed.'
    }
}
finally {
    $env:ENVIRONMENT = $previousEnvironment
    $env:LLM_ENABLED = $previousLlm
}

Write-Host "Kubernetes scenario '$Scenario' completed. See .incidentpilot-kubernetes-run.json for the trace." -ForegroundColor Green
