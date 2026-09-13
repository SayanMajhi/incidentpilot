[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$failed = $false

function Show-ToolStatus {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        Write-Host ("{0,-12} OK ({1})" -f "$Name`:", $command.Source) -ForegroundColor Green
        return $true
    }
    Write-Host ("{0,-12} MISSING" -f "$Name`:") -ForegroundColor Red
    return $false
}

$dockerFound = Show-ToolStatus 'docker'
$kubectlFound = Show-ToolStatus 'kubectl'
$kindFound = Show-ToolStatus 'kind'

if ($dockerFound) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Docker:      RUNNING' -ForegroundColor Green
    }
    else {
        Write-Host 'Docker:      UNREACHABLE (start Docker Desktop)' -ForegroundColor Red
        $failed = $true
    }
}
else {
    $failed = $true
}

if ($kubectlFound) {
    $context = kubectl config current-context 2>$null
    if ($LASTEXITCODE -eq 0 -and $context) {
        Write-Host "Context:     $context"
        kubectl cluster-info *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host 'Cluster:     REACHABLE' -ForegroundColor Green
        }
        else {
            Write-Host 'Cluster:     UNREACHABLE (check Docker and kubectl context)' -ForegroundColor Red
            $failed = $true
        }
    }
    else {
        Write-Host 'Context:     NONE' -ForegroundColor Red
        Write-Host 'Cluster:     UNREACHABLE' -ForegroundColor Red
        $failed = $true
    }
}
else {
    $failed = $true
}

if ($kindFound) {
    $clusters = @(kind get clusters 2>$null)
    $clusterStatus = if ($clusters -contains 'incidentpilot') { 'EXISTS' } else { 'MISSING' }
    Write-Host "kind cluster: $clusterStatus"
}
else {
    Write-Host 'kind cluster: UNKNOWN (kind is not installed)' -ForegroundColor Yellow
}

if ($failed) {
    exit 1
}

Write-Host 'Kubernetes demo prerequisites are ready.' -ForegroundColor Green
