[CmdletBinding()]
param(
    [string] $RepoRoot = "",
    [string] $PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

function Resolve-RepositoryRoot {
    param([string] $RequestedRoot)

    if ($RequestedRoot) {
        $resolved = (Resolve-Path -LiteralPath $RequestedRoot).Path
        if (-not (Test-Path -LiteralPath (Join-Path $resolved "pyproject.toml"))) {
            throw "The requested repository root does not contain pyproject.toml: $resolved"
        }
        return $resolved
    }

    $candidate = (Get-Location).Path
    while ($candidate) {
        if (Test-Path -LiteralPath (Join-Path $candidate "pyproject.toml")) {
            return $candidate
        }

        $parent = Split-Path -Parent $candidate
        if (-not $parent -or $parent -eq $candidate) {
            break
        }
        $candidate = $parent
    }

    throw "Unable to locate the Batch-87 repository root from the current directory."
}

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory)]
        [string] $Label,

        [Parameter(Mandatory)]
        [scriptblock] $Command,

        [int[]] $AllowedExitCodes = @(0)
    )

    Write-Host ""
    Write-Host "=== $Label ==="
    & $Command
    $exitCode = $LASTEXITCODE

    if ($null -eq $exitCode) {
        $exitCode = 0
    }

    if ($AllowedExitCodes -notcontains $exitCode) {
        throw "$Label failed with exit code $exitCode."
    }

    Write-Host "PASS: $Label (exit code $exitCode)"
    return $exitCode
}

$RepoRoot = Resolve-RepositoryRoot -RequestedRoot $RepoRoot
Set-Location -LiteralPath $RepoRoot

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDirectory = Join-Path $RepoRoot "artifacts\validation-runs\d0-$timestamp"
$transcriptPath = Join-Path $runDirectory "B87-D0-Validation-Transcript-$timestamp.txt"
$summaryPath = Join-Path $runDirectory "B87-D0-Validation-Summary-$timestamp.md"
$jsonPath = Join-Path $runDirectory "B87-D0-Conformance-$timestamp.json"
$bundlePath = Join-Path $runDirectory "B87-D0-Validation-Bundle-$timestamp.zip"

New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null

$startedAt = Get-Date
$success = $false
$failureMessage = $null
$prepState = "not-run"
$branchName = "unknown"
$commitSha = "unknown"
$pythonVersion = "unknown"
$pipVersion = "unknown"

Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null

try {
    Write-Host "B87-D0 CLOSURE VALIDATION RUN"
    Write-Host "Repository: $RepoRoot"
    Write-Host "Started: $($startedAt.ToString('o'))"

    $branchName = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to determine the current Git branch."
    }

    $commitSha = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to determine the current Git commit."
    }

    $pythonVersion = (& $PythonCommand --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to run Python using command '$PythonCommand'."
    }

    $pipVersion = (& $PythonCommand -m pip --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "pip is unavailable for '$PythonCommand'."
    }

    Write-Host "Branch: $branchName"
    Write-Host "Commit: $commitSha"
    Write-Host "Python: $pythonVersion"
    Write-Host "pip: $pipVersion"

    Invoke-NativeChecked `
        -Label "INSTALL DEVELOPMENT DEPENDENCIES" `
        -Command { & $PythonCommand -m pip install -e ".[dev]" } | Out-Null

    Invoke-NativeChecked `
        -Label "VERIFY PYTEST INSTALLATION" `
        -Command { & $PythonCommand -m pytest --version } | Out-Null

    Write-Host ""
    Write-Host "=== PREVIEW SOURCE PREPARATION ==="
    & $PythonCommand scripts/prepare_d0_closure_sources.py --check --show-diff
    $prepExitCode = $LASTEXITCODE

    if ($prepExitCode -eq 0) {
        $prepState = "already-prepared"
        Write-Host "PASS: D0 source documents were already prepared."
    }
    elseif ($prepExitCode -eq 1) {
        $prepState = "required-and-applied"
        Write-Host "Source preparation is required; applying the idempotent amendment."
        Invoke-NativeChecked `
            -Label "APPLY SOURCE PREPARATION" `
            -Command { & $PythonCommand scripts/prepare_d0_closure_sources.py } | Out-Null
    }
    else {
        throw "Source-preparation preview failed with unexpected exit code $prepExitCode."
    }

    Invoke-NativeChecked `
        -Label "VERIFY SOURCE PREPARATION IDEMPOTENCE" `
        -Command { & $PythonCommand scripts/prepare_d0_closure_sources.py --check } | Out-Null

    Invoke-NativeChecked `
        -Label "RUN PYTEST" `
        -Command { & $PythonCommand -m pytest } | Out-Null

    Invoke-NativeChecked `
        -Label "RUN D0 ARCHITECTURE CONFORMANCE" `
        -Command {
            & $PythonCommand scripts/validate_d0_architecture.py `
                --json-output $jsonPath
        } | Out-Null

    Invoke-NativeChecked `
        -Label "RUN GIT DIFF CHECK" `
        -Command { & git diff --check } | Out-Null

    Write-Host ""
    Write-Host "=== GIT DIFF STAT ==="
    & git diff --stat
    if ($LASTEXITCODE -ne 0) {
        throw "git diff --stat failed."
    }

    Write-Host ""
    Write-Host "=== GIT STATUS ==="
    & git status --short
    if ($LASTEXITCODE -ne 0) {
        throw "git status --short failed."
    }

    $success = $true
}
catch {
    $failureMessage = $_.Exception.Message
    Write-Host ""
    Write-Host "VALIDATION FAILED: $failureMessage"
}
finally {
    $finishedAt = Get-Date
    Stop-Transcript | Out-Null
}

$statusText = if ($success) { "PASS" } else { "FAIL" }
$jsonRelative = if (Test-Path -LiteralPath $jsonPath) {
    $jsonPath.Substring($RepoRoot.Length).TrimStart('\')
}
else {
    "Not produced"
}

$summary = @"
# B87-D0 Validation Run Summary

**Status:** $statusText  
**Started:** $($startedAt.ToString('o'))  
**Finished:** $($finishedAt.ToString('o'))  
**Repository:** `$RepoRoot`  
**Branch:** `$branchName`  
**Commit:** `$commitSha`  
**Python:** `$pythonVersion`  
**pip:** `$pipVersion`  
**Source preparation:** `$prepState`

## Result

$(if ($success) {
    "The D0 source-preparation, pytest, architecture-conformance, and Git diff checks completed without a command failure. Closure blockers reported by the conformance validator still require Nolan–Byte review and are not converted into approval by this run."
} else {
    "The run stopped at the first failing command. Failure: **$failureMessage**"
})

## Shareable artefacts

- Full transcript: `$(Split-Path -Leaf $transcriptPath)`
- Summary: `$(Split-Path -Leaf $summaryPath)`
- Conformance JSON: `$jsonRelative`
- Bundle: `$(Split-Path -Leaf $bundlePath)`

## Interpretation boundary

This run validates machine-testable document structure, declared invariants,
traceability, tests, and repository diff integrity. It does not replace the
Nolan–Byte semantic architecture review and does not validate future model
behaviour.
"@

[System.IO.File]::WriteAllText(
    $summaryPath,
    $summary,
    [System.Text.UTF8Encoding]::new($false)
)

$bundleItems = @($transcriptPath, $summaryPath)
if (Test-Path -LiteralPath $jsonPath) {
    $bundleItems += $jsonPath
}

Compress-Archive -LiteralPath $bundleItems -DestinationPath $bundlePath -Force

Write-Host ""
Write-Host "============================================================"
Write-Host "B87-D0 VALIDATION ARTEFACTS"
Write-Host "============================================================"
Write-Host "Summary:    $summaryPath"
Write-Host "Transcript: $transcriptPath"
Write-Host "JSON:       $jsonPath"
Write-Host "Bundle:     $bundlePath"

if (-not $success) {
    throw "B87-D0 validation failed. Share the generated bundle for review. $failureMessage"
}

Write-Host ""
Write-Host "PASS: B87-D0 validation run completed. Share the generated ZIP bundle for review."
