# install-context-debugger.ps1
# One-click global installer for Project Context / Context Debugger.
#
# Expected layout:
#   C:\Projects\project-context\install-context-debugger.ps1
#   C:\Projects\project-context\integrations\opencode\src\index.ts
#
# OpenCode V2 auto-discovers plugin package directories under:
#   %USERPROFILE%\.config\opencode\plugins\
#
# This installer deliberately DOES NOT edit opencode.jsonc, so existing
# plugin entries such as file:///C:/Projects/opencode-remembering remain intact.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedOpenCodeVersion = "2.0.16"
$PluginName = "context-debugger"

$RepoRoot = $PSScriptRoot
$SourceDir = Join-Path $RepoRoot "integrations\opencode\src"

$ConfigDir = Join-Path $env:USERPROFILE ".config\opencode"
$ConfigFile = Join-Path $ConfigDir "opencode.jsonc"
$PluginsDir = Join-Path $ConfigDir "plugins"
$InstallDir = Join-Path $PluginsDir $PluginName
$BackupRoot = Join-Path $ConfigDir "plugin-backups"

$SpoolDir = Join-Path $env:USERPROFILE ".local\share\project-context\captures"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "INSTALL FAILED" -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    exit 1
}

function Get-OpenCodeVersion {
    $command = Get-Command "opencode" -ErrorAction SilentlyContinue
    if (-not $command) {
        Fail "OpenCode is not on PATH. Expected OpenCode $ExpectedOpenCodeVersion."
    }

    $raw = (& opencode --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not determine OpenCode version. Output: $raw"
    }

    $match = [regex]::Match($raw, '\d+\.\d+\.\d+')
    if (-not $match.Success) {
        Fail "Could not parse OpenCode version from: $raw"
    }

    return $match.Value
}

Write-Host ""
Write-Host "Project Context - Context Debugger Installer" -ForegroundColor Green
Write-Host "------------------------------------------------"
Write-Host "Repository : $RepoRoot"
Write-Host "Config     : $ConfigFile"
Write-Host "Plugin     : $InstallDir"
Write-Host "Capture    : $SpoolDir"

Write-Step "Checking Context Debugger plugin source"

if (-not (Test-Path -LiteralPath $SourceDir -PathType Container)) {
    Fail "Plugin source directory not found: $SourceDir`nPlace this script at the project-context repository root."
}

$RequiredFiles = @(
    "index.ts",
    "capture.ts",
    "schema.ts"
)

foreach ($file in $RequiredFiles) {
    $path = Join-Path $SourceDir $file
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Fail "Required plugin file not found: $path"
    }
}

Write-Host "Plugin source looks good." -ForegroundColor Green

Write-Step "Checking OpenCode version"

$InstalledOpenCodeVersion = Get-OpenCodeVersion

if ($InstalledOpenCodeVersion -ne $ExpectedOpenCodeVersion) {
    Fail @"
This Context Debugger build targets exactly OpenCode $ExpectedOpenCodeVersion.
Installed OpenCode is $InstalledOpenCodeVersion.

No compatibility fallback will be installed.
Update project-context for the installed OpenCode version, or install the
supported OpenCode version, then run this script again.
"@
}

Write-Host "OpenCode $InstalledOpenCodeVersion matches the pinned target." -ForegroundColor Green

Write-Step "Preparing global OpenCode plugin directory"

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path $PluginsDir | Out-Null
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
New-Item -ItemType Directory -Force -Path $SpoolDir | Out-Null

if (Test-Path -LiteralPath $ConfigFile -PathType Leaf) {
    Write-Host "Found existing config: $ConfigFile"
    Write-Host "It will NOT be modified." -ForegroundColor Yellow
} else {
    Write-Host "No opencode.jsonc found at $ConfigFile."
    Write-Host "That is OK: global plugin auto-discovery does not require a config edit." -ForegroundColor Yellow
}

if (Test-Path -LiteralPath $InstallDir) {
    Write-Step "Backing up previous Context Debugger installation"

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = Join-Path $BackupRoot "$PluginName-$stamp"

    Move-Item -LiteralPath $InstallDir -Destination $backupDir
    Write-Host "Previous installation moved to:"
    Write-Host "  $backupDir"
}

Write-Step "Installing Context Debugger globally"

$tempDir = Join-Path $ConfigDir (".context-debugger-install-" + [guid]::NewGuid().ToString("N"))

try {
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

    Copy-Item -Path (Join-Path $SourceDir "*") -Destination $tempDir -Recurse -Force

    foreach ($file in $RequiredFiles) {
        $installed = Join-Path $tempDir $file
        if (-not (Test-Path -LiteralPath $installed -PathType Leaf)) {
            throw "Copied installation is missing $file"
        }
    }

    Move-Item -LiteralPath $tempDir -Destination $InstallDir
}
catch {
    if (Test-Path -LiteralPath $tempDir) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Fail "Could not install Context Debugger: $($_.Exception.Message)"
}

Write-Host "Installed:" -ForegroundColor Green
Write-Host "  $InstallDir"

Write-Step "Enabling local Context Debugger capture"

[Environment]::SetEnvironmentVariable(
    "PROJECT_CONTEXT_CAPTURE",
    "1",
    [EnvironmentVariableTarget]::User
)

[Environment]::SetEnvironmentVariable(
    "PROJECT_CONTEXT_SPOOL_DIR",
    $SpoolDir,
    [EnvironmentVariableTarget]::User
)

$env:PROJECT_CONTEXT_CAPTURE = "1"
$env:PROJECT_CONTEXT_SPOOL_DIR = $SpoolDir

Write-Host "PROJECT_CONTEXT_CAPTURE=1" -ForegroundColor Green
Write-Host "PROJECT_CONTEXT_SPOOL_DIR=$SpoolDir" -ForegroundColor Green

Write-Step "Verifying installation"

$InstalledFiles = Get-ChildItem -LiteralPath $InstallDir -File -Recurse

if (-not $InstalledFiles) {
    Fail "Installation directory is empty: $InstallDir"
}

foreach ($file in $RequiredFiles) {
    $path = Join-Path $InstallDir $file
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Fail "Installed plugin is missing required file: $path"
    }
}

$userCapture = [Environment]::GetEnvironmentVariable(
    "PROJECT_CONTEXT_CAPTURE",
    [EnvironmentVariableTarget]::User
)
$userSpool = [Environment]::GetEnvironmentVariable(
    "PROJECT_CONTEXT_SPOOL_DIR",
    [EnvironmentVariableTarget]::User
)

if ($userCapture -ne "1") {
    Fail "PROJECT_CONTEXT_CAPTURE was not persisted correctly."
}

if ($userSpool -ne $SpoolDir) {
    Fail "PROJECT_CONTEXT_SPOOL_DIR was not persisted correctly."
}

Write-Host ""
Write-Host "INSTALL COMPLETE" -ForegroundColor Green
Write-Host "------------------------------------------------"
Write-Host "OpenCode          : $InstalledOpenCodeVersion"
Write-Host "Plugin API        : V2"
Write-Host "Context Debugger  : $InstallDir"
Write-Host "Capture spool     : $SpoolDir"
Write-Host "Existing config   : untouched"
Write-Host ""
Write-Host "Your existing plugin configuration remains intact, including entries"
Write-Host "such as file:///C:/Projects/opencode-remembering."
Write-Host ""
Write-Host "OpenCode auto-discovers the Context Debugger from its global plugins"
Write-Host "directory. Open a NEW OpenCode process so it inherits the persisted"
Write-Host "capture environment variables."
Write-Host ""
Write-Host "After doing some normal work, inspect it with:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  contextlab debug latest `"$SpoolDir`""
Write-Host "  contextlab debug timeline `"$SpoolDir`""
Write-Host "  contextlab debug doctor `"$SpoolDir`""
Write-Host ""
Write-Host "No OpenCode process was started, stopped, killed, or restarted by this installer."
Write-Host ""
