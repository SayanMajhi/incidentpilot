<#
.SYNOPSIS
    One-time cleanup after the backend was reorganised into `backend/`.

.DESCRIPTION
    The Python packages that used to sit at the repository root now live under
    `backend/`, and a handful of dead files were dropped. The new files are
    already in place; this script removes only the superseded copies and build
    artefacts, then re-runs the test suite to prove nothing was lost.

    Run it once, from the repository root:

        powershell -ExecutionPolicy Bypass -File scripts\finish_restructure.ps1

    Delete this script afterwards - it has no further purpose.
#>

[CmdletBinding()]
param(
    # Show what would be removed without removing anything.
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
Write-Host "Repository root: $repoRoot" -ForegroundColor Cyan

# Refuse to run before the new layout exists, so this can never delete the
# only copy of the backend.
$required = @(
    'backend/agent/controller.py',
    'backend/simulator/service.py',
    'backend/tools/remediation.py',
    'backend/safety/policy.py',
    'backend/verification/verifier.py',
    'backend/shared/slo.py'
)
$missing = $required | Where-Object { -not (Test-Path $_) }
if ($missing) {
    Write-Host 'Aborting: the new backend/ layout is incomplete.' -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  missing $_" -ForegroundColor Red }
    exit 1
}

# Superseded locations and dead files. Everything here has either moved under
# backend/ or was removed as unused.
$stale = @(
    # Python packages that moved into backend/
    'agent',
    'safety',
    'simulator',
    'tools',
    'verification',

    # Renamed: it was collected as a test but is a manual connectivity check
    'scripts/test_qwen_connection.py',

    # Empty placeholder test package
    'tests/evaluation',

    # Frontend files that nothing imported
    'frontend/src/components/IncidentPilot/InspectionSidebar.tsx',
    'frontend/src/styles/dashboard.css',

    # Build artefacts and caches (all now git-ignored)
    'frontend/dist',
    'frontend/tsconfig.tsbuildinfo',
    '.pytest_cache'
)

$isGitRepo = Test-Path (Join-Path $repoRoot '.git')
$removed = @()

foreach ($path in $stale) {
    if (-not (Test-Path $path)) { continue }

    if ($DryRun) {
        Write-Host "would remove $path" -ForegroundColor Yellow
        continue
    }

    if ($isGitRepo) {
        # Keep Git's index in step for anything it is tracking.
        git rm -r --quiet --ignore-unmatch -- $path 2>$null | Out-Null
    }
    if (Test-Path $path) {
        Remove-Item -Recurse -Force -- $path
    }
    Write-Host "removed $path" -ForegroundColor Green
    $removed += $path
}

# Stray bytecode caches left behind by the old layout.
$pycache = Get-ChildItem -Path $repoRoot -Recurse -Force -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\(\.venv|node_modules)\\' }
foreach ($dir in $pycache) {
    if ($DryRun) {
        Write-Host "would remove $($dir.FullName)" -ForegroundColor Yellow
    } else {
        Remove-Item -Recurse -Force -- $dir.FullName
        Write-Host "removed $($dir.FullName)" -ForegroundColor Green
    }
}

if ($DryRun) {
    Write-Host "`nDry run only - nothing was changed." -ForegroundColor Cyan
    exit 0
}

Write-Host "`nRemoved $($removed.Count) stale path(s). Verifying..." -ForegroundColor Cyan

$python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Tests failed. Inspect the output above before committing.' -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "`nCleanup complete. The repository is on the new layout." -ForegroundColor Green
Write-Host 'You can now delete scripts\finish_restructure.ps1.' -ForegroundColor Green
