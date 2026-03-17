########################################################################
# Build ITK Python wheel tarballs (build cache) on Windows.
#
# This is the Windows PowerShell equivalent of make_tarballs.sh.
# POSIX shell is not supported for this workflow on Windows.
#
# This script builds the ITK core cache only — it has no knowledge of
# external modules. Module-specific flags (--module-source-dir,
# --module-dependencies-root-dir, --itk-module-deps, --lib-paths) are
# intentionally absent; they belong only in the module wheel build script.
#
# Directory names are intentionally kept short to avoid Windows MAX_PATH
# issues during deep CMake/compiler builds. Everything lives under one
# root directory (C:\BDR) so no build artifacts are scattered at C:\:
#   ITKPythonPackage  ->  C:\BDR\IPP   (scripts clone)
#   ITK source        ->  C:\BDR\ITK   (ITK git checkout)
#   build root        ->  C:\BDR       (build_wheels.py root; cached build lands at C:\BDR\build\ITK-windows-...)
#
# This script MUST be run from the canonical location:
#   C:\BDR\IPP\scripts\make_tarballs.ps1
#
# Typical usage:
#   > $env:ITK_GIT_TAG = "v6.0b02"
#   > .\make_tarballs.ps1
#
# Restrict to specific python versions by passing them as arguments:
#   > .\make_tarballs.ps1 py311
#
# -----------------------------------------------------------------------
# Environment variables:
#
# `$env:ITK_GIT_TAG`
#     ITK git tag to build from. Falls back to v6.0b02 with loud warnings
#     if unset, matching the bash script behaviour.
#
########################################################################
param (
  [Parameter(ValueFromRemainingArguments)]
  [string[]]$pyenvs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Resolve python environments
if (-not $pyenvs -or $pyenvs.Count -eq 0) {
  $pyenvs = @("py310", "py311")
}
echo "Building for python environments: $($pyenvs -join ', ')"

# Resolve ITK_GIT_TAG — loud warning if unset, matching bash behaviour
$DEFAULT_ITK_GIT_TAG = "v6.0b02"
if (-not $env:ITK_GIT_TAG) {
  $warningLine = "===== WARNING: ITK_GIT_TAG not set, so defaulting to $DEFAULT_ITK_GIT_TAG"
  echo "============================================================================="
  1..29 | ForEach-Object { echo $warningLine }
  echo "============================================================================="
  $env:ITK_GIT_TAG = $DEFAULT_ITK_GIT_TAG
}
$ITK_GIT_TAG = $env:ITK_GIT_TAG
echo "ITK_GIT_TAG : $ITK_GIT_TAG"

# Compute paths from this script's location.
# Everything is contained under C:\BDR to keep all build artifacts in one
# place and avoid spreading directories across the drive root.
#
#   C:\BDR\               <- $BDR          (single root for all build content)
#   C:\BDR\IPP\scripts\   <- $ScriptsDir   (this file)
#   C:\BDR\IPP\           <- $IPPDir       (ITKPythonPackage clone)
#   C:\BDR\ITK\           <- $ItkSourceDir (ITK git checkout)
#   C:\BDR\               <- $BuildDirRoot (build root; cached build lands at C:\BDR\build\ITK-windows-...)
#   C:\BDR\.pixi\         <- pixi home
$BDR          = "C:\BDR"
$ScriptsDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$IPPDir       = Split-Path -Parent $ScriptsDir
$BuildScript  = Join-Path $ScriptsDir "build_wheels.py"
$ItkSourceDir = Join-Path $BDR "ITK"
$BuildDirRoot = $BDR

echo "BDR          : $BDR"
echo "IPPDir       : $IPPDir"
echo "ScriptsDir   : $ScriptsDir"
echo "ItkSourceDir : $ItkSourceDir"
echo "BuildDirRoot : $BuildDirRoot"

# Validate script is running from the expected canonical location
$ExpectedScriptsDir = Join-Path $BDR "IPP\scripts"
if ($ScriptsDir -ne $ExpectedScriptsDir) {
  Write-Error @"
ERROR: GitHub CI requires a rigid directory structure.
Script found at  : $ScriptsDir
Expected location: $ExpectedScriptsDir

  RUN: cd $BDR
  RUN: git clone git@github.com:<org>/ITKPythonPackage.git $BDR\IPP
  FOR DEVELOPMENT: git checkout python_based_build_scripts
  RUN: $ExpectedScriptsDir\make_windows_zip.ps1
"@
  exit 1
}

if (-not (Test-Path -LiteralPath $BuildScript)) {
  throw "build_wheels.py not found at: $BuildScript"
}

# Create BDR if it doesn't exist
# (may require administrator credentials on a fresh machine)
if (-not (Test-Path -LiteralPath $BDR)) {
  echo "Creating directory: $BDR"
  New-Item -ItemType Directory -Path $BDR -Force | Out-Null
}

# Install pixi if not already present.
# Python, Doxygen, and all build tools are provided by the pixi environment.
$env:PIXI_HOME = "$BDR\.pixi"
if (-not (Test-Path "$env:PIXI_HOME\bin\pixi.exe")) {
  echo "Installing pixi..."
  Invoke-WebRequest -Uri "https://pixi.sh/install.ps1" -OutFile "install-pixi.ps1"
  powershell -ExecutionPolicy Bypass -File "install-pixi.ps1"
}
$env:Path = "$env:PIXI_HOME\bin;$env:Path"

# Build each requested python environment.
# Push-Location/finally ensures we always restore the caller's directory.
Push-Location $IPPDir
try {
  foreach ($pyenv in $pyenvs) {
    # Normalise any of: py311 / py3.11 / cp311 / 3.11  ->  py311
    $pySquashed  = $pyenv -replace 'py|cp|\.', ''
    $pyenv       = "py$pySquashed"
    $platformEnv = "windows-$pyenv"

    echo ""
    echo "========================================================"
    echo "Building cache for platform env: $platformEnv"
    echo "========================================================"

    pixi run -e $platformEnv python $BuildScript `
      --platform-env        $platformEnv `
      --build-itk-tarball-cache `
      --build-dir-root      $BuildDirRoot `
      --itk-source-dir      $ItkSourceDir `
      --itk-git-tag         $ITK_GIT_TAG `
      --no-use-sudo `
      --no-use-ccache

    if ($LASTEXITCODE -ne 0) {
      throw "build_wheels.py failed for $platformEnv (exit code $LASTEXITCODE)"
    }
  }
}
finally {
  Pop-Location
}

echo ""
echo "All tarball builds completed successfully."
