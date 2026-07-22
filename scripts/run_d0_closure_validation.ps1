[CmdletBinding()]
param(
    [string] $RepoRoot = "",
    [string] $PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

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

        [int[]] $AllowedExitCodes = @(0),

        [string] $LogPath = ""
    )

    Write-Host ""
    Write-Host "=== $Label ==="

    $output = @(& $Command 2>&1)
    $exitCode = $LASTEXITCODE

    if ($null -eq $exitCode) {
        $exitCode = 0
    }

    $renderedOutput = @(
        $output | ForEach-Object {
            if ($null -eq $_) {
                ""
            }
            else {
                $_.ToString()
            }
        }
    )

    foreach ($line in $renderedOutput) {
        Write-Host $line
    }

    if ($LogPath) {
        $logDirectory = Split-Path -Parent $LogPath
        if ($logDirectory) {
            New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
        }

        $logContent = @(
            "Label: $Label"
            "Exit code: $exitCode"
            ""
            $renderedOutput
        )

        [System.IO.File]::WriteAllLines(
            $LogPath,
            $logContent,
            [System.Text.UTF8Encoding]::new($false)
        )
    }

    if ($AllowedExitCodes -notcontains $exitCode) {
        throw "$Label failed with exit code $exitCode."
    }

    Write-Host "PASS: $Label (exit code $exitCode)"

    return [pscustomobject]@{
        Label = $Label
        ExitCode = $exitCode
        Output = $renderedOutput
        LogPath = $LogPath
    }
}

$RepoRoot = Resolve-RepositoryRoot -RequestedRoot $RepoRoot
Set-Location -LiteralPath $RepoRoot

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDirectory = Join-Path $RepoRoot "artifacts\validation-runs\d0-$timestamp"
$logsDirectory = Join-Path $runDirectory "logs"
$transcriptPath = Join-Path $runDirectory "B87-D0-Validation-Transcript-$timestamp.txt"
$summaryPath = Join-Path $runDirectory "B87-D0-Validation-Summary-$timestamp.md"
$jsonPath = Join-Path $runDirectory "B87-D0-Conformance-$timestamp.json"
$bundlePath = Join-Path $runDirectory "B87-D0-Validation-Bundle-$timestamp.zip"

New-Item -ItemType Directory -Path $logsDirectory -Force | Out-Null

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

    $branchResult = Invoke-NativeChecked `
        -Label "READ CURRENT BRANCH" `
        -Command { & git branch --show-current } `
        -LogPath (Join-Path $logsDirectory "01-current-branch.log")
    $branchName = ($branchResult.Output -join "`n").Trim()

    $commitResult = Invoke-NativeChecked `
        -Label "READ CURRENT COMMIT" `
        -Command { & git rev-parse HEAD } `
        -LogPath (Join-Path $logsDirectory "02-current-commit.log")
    $commitSha = ($commitResult.Output -join "`n").Trim()

    $pythonResult = Invoke-NativeChecked `
        -Label "READ PYTHON VERSION" `
        -Command { & $PythonCommand --version } `
        -LogPath (Join-Path $logsDirectory "03-python-version.log")
    $pythonVersion = ($pythonResult.Output -join "`n").Trim()

    $pipResult = Invoke-NativeChecked `
        -Label "READ PIP VERSION" `
        -Command { & $PythonCommand -m pip --version } `
        -LogPath (Join-Path $logsDirectory "04-pip-version.log")
    $pipVersion = ($pipResult.Output -join "`n").Trim()

    Write-Host "Branch: $branchName"
    Write-Host "Commit: $commitSha"
    Write-Host "Python: $pythonVersion"
    Write-Host "pip: $pipVersion"

    $null = Invoke-NativeChecked `
        -Label "INSTALL D0 VALIDATION DEPENDENCIES" `
        -Command { & $PythonCommand -m pip install "pytest>=8" } `
        -LogPath (Join-Path $logsDirectory "05-install-validation-dependencies.log")

    $null = Invoke-NativeChecked `
        -Label "VERIFY PYTEST INSTALLATION" `
        -Command { & $PythonCommand -m pytest --version } `
        -LogPath (Join-Path $logsDirectory "06-pytest-version.log")

    $prepResult = Invoke-NativeChecked `
        -Label "PREVIEW SOURCE PREPARATION" `
        -Command {
            & $PythonCommand scripts/prepare_d0_closure_sources.py --check --show-diff
        } `
        -AllowedExitCodes @(0, 1) `
        -LogPath (Join-Path $logsDirectory "07-source-preparation-preview.log")

    if ($prepResult.ExitCode -eq 0) {
        $prepState = "already-prepared"
        Write-Host "PASS: D0 source documents were already prepared."
    }
    elseif ($prepResult.ExitCode -eq 1) {
        $prepState = "required-and-applied"
        Write-Host "Source preparation is required; applying the idempotent amendment."

        $null = Invoke-NativeChecked `
            -Label "APPLY SOURCE PREPARATION" `
            -Command { & $PythonCommand scripts/prepare_d0_closure_sources.py } `
            -LogPath (Join-Path $logsDirectory "08-source-preparation-apply.log")
    }
    else {
        throw "Source-preparation preview failed with unexpected exit code $($prepResult.ExitCode)."
    }

    $null = Invoke-NativeChecked `
        -Label "VERIFY SOURCE PREPARATION IDEMPOTENCE" `
        -Command { & $PythonCommand scripts/prepare_d0_closure_sources.py --check } `
        -LogPath (Join-Path $logsDirectory "09-source-preparation-idempotence.log")

    $null = Invoke-NativeChecked `
        -Label "RUN PYTEST" `
        -Command { & $PythonCommand -m pytest } `
        -LogPath (Join-Path $logsDirectory "10-pytest.log")

    $null = Invoke-NativeChecked `
        -Label "RUN D0 ARCHITECTURE CONFORMANCE" `
        -Command {
            & $PythonCommand scripts/validate_d0_architecture.py `
                --json-output $jsonPath
        } `
        -LogPath (Join-Path $logsDirectory "11-architecture-conformance.log")

    $null = Invoke-NativeChecked `
        -Label "RUN GIT DIFF CHECK" `
        -Command { & git diff --check } `
        -LogPath (Join-Path $logsDirectory "12-git-diff-check.log")

    $null = Invoke-NativeChecked `
        -Label "READ GIT DIFF STAT" `
        -Command { & git diff --stat } `
        -LogPath (Join-Path $logsDirectory "13-git-diff-stat.log")

    $null = Invoke-NativeChecked `
        -Label "READ GIT STATUS" `
        -Command { & git status --short } `
        -LogPath (Join-Path $logsDirectory "14-git-status.log")

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

$stepLogs = @(
    Get-ChildItem -LiteralPath $logsDirectory -File -ErrorAction SilentlyContinue |
        Sort-Object Name |
        ForEach-Object { $_.Name }
)

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
- Step logs: `logs\`
- Bundle: `$(Split-Path -Leaf $bundlePath)`

## Captured step logs

$(if ($stepLogs.Count -gt 0) {
    ($stepLogs | ForEach-Object { "- `$_`" }) -join "`n"
} else {
    "No step logs were produced."
})

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

$bundleItems = @($transcriptPath, $summaryPath, $logsDirectory)
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
Write-Host "Step logs:  $logsDirectory"
Write-Host "Bundle:     $bundlePath"

if (-not $success) {
    throw "B87-D0 validation failed. Share the generated bundle for review. $failureMessage"
}

Write-Host ""
Write-Host "PASS: B87-D0 validation run completed. Share the generated ZIP bundle for review."
