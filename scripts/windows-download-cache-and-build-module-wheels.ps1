########################################################################
# Pull build dependencies and build an ITK external module on Windows.
#
# This script must be run in an x64 Developer PowerShell.
# See https://learn.microsoft.com/en-us/visualstudio/ide/reference/command-prompt-powershell?view=vs-2022#developer-powershell
#
# -----------------------------------------------------------------------
# Positional parameters / named options:
#
# -python_version_minor  Python minor version (required).
#     For instance, for Python 3.11:
#     > windows-download-cache-and-build-module-wheels.ps1 -python_version_minor 11
#     or positionally:
#     > windows-download-cache-and-build-module-wheels.ps1 11
#
# -setup_options         pyproject.toml options forwarded to the build script.
#     For instance, to exclude a library during packaging:
#     > ... -setup_options "--exclude-libs nvcuda.dll"
#
# -cmake_options         CMake options passed to pyproject.toml for project configuration.
#     For instance:
#     > ... -cmake_options "-DRTK_USE_CUDA:BOOL=ON"
#
# -----------------------------------------------------------------------
# Environment variables used in this script:
#
# `$env:ITK_PACKAGE_VERSION`
#     Tag for the ITKPythonBuilds archive to download/use. Required.
#
# `$env:ITKPYTHONPACKAGE_TAG`
#     Tag for ITKPythonPackage build scripts to use.
#     If empty, the scripts bundled in the archive will be used.
#
# `$env:ITKPYTHONPACKAGE_ORG`
#     GitHub organization/user for ITKPythonPackage. Default: InsightSoftwareConsortium.
#     Ignored if ITKPYTHONPACKAGE_TAG is empty.
#
# `$env:ITK_MODULE_PREQ`
#     Colon-delimited list of ITK module dependencies.
#     Format: `<org>/<module>@<tag>:<org>/<module>@<tag>:...`
#     Example: `InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0`
#     Passed directly to build_wheels.py via --itk-module-deps.
#
# `$env:MODULE_SRC_DIRECTORY`
#     Path to the ITK external module source. Defaults to the directory
#     containing this script.
#
########################################################################
param (
  [int]$python_version_minor,
  [string]$setup_options = "",
  [string]$cmake_options = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Validate required inputs
if (-not $python_version_minor) {
  Write-Error "ERROR: -python_version_minor is required. Example: -python_version_minor 11"
  exit 1
}
if (-not $env:ITK_PACKAGE_VERSION) {
  Write-Error "ERROR: `$env:ITK_PACKAGE_VERSION must be set before running this script."
  exit 1
}

# Resolve configuration
$MODULE_SRC_DIRECTORY = if ($env:MODULE_SRC_DIRECTORY) {
  $env:MODULE_SRC_DIRECTORY
} else {
  $PSScriptRoot
}
echo "MODULE_SRC_DIRECTORY: $MODULE_SRC_DIRECTORY"

$ITK_PACKAGE_VERSION   = $env:ITK_PACKAGE_VERSION
# For backwards compatibility when the ITK_GIT_TAG was required to match the ITK_PACKAGE_VERSION
$ITK_GIT_TAG           = if ($env:ITK_GIT_TAG) { $env:ITK_GIT_TAG } else { $ITK_PACKAGE_VERSION }
$ITKPYTHONPACKAGE_ORG  = if ($env:ITKPYTHONPACKAGE_ORG) { $env:ITKPYTHONPACKAGE_ORG } else { "InsightSoftwareConsortium" }
$ITKPYTHONPACKAGE_TAG  = if ($env:ITKPYTHONPACKAGE_TAG)  { $env:ITKPYTHONPACKAGE_TAG  } else { "" }

$DASHBOARD_BUILD_DIRECTORY = "C:\BDR"
$platformEnv = "windows-py3$python_version_minor"

echo "Python version     : 3.$python_version_minor"
echo "ITK_PACKAGE_VERSION: $ITK_PACKAGE_VERSION"
echo "ITK_GIT_TAG        : $ITK_GIT_TAG"
echo "Platform env       : $platformEnv"

# Install pixi and required global tools
# NOTE: Python and Doxygen are provided by the pixi environment; no need to
#       install them separately here.
$env:PIXI_HOME = "$DASHBOARD_BUILD_DIRECTORY\.pixi"
if (-not (Test-Path "$env:PIXI_HOME\bin\pixi.exe")) {
  echo "Installing pixi..."
  Invoke-WebRequest -Uri "https://pixi.sh/install.ps1" -OutFile "install-pixi.ps1"
  powershell -ExecutionPolicy Bypass -File "install-pixi.ps1"
}
$env:Path = "$env:PIXI_HOME\bin;$env:Path"

# Install global packages via pixi for use in this script
# Note: Using conda-forge packages that are available on Windows
echo "Installing global tools via pixi..."
$globalPackages = @(
  "git",          # Required for cloning ITKPythonPackage repo
  "aria2"         # Fast download utility (cross-platform)
)

foreach ($pkg in $globalPackages) {
  echo "  Installing $pkg..."
  try {
    & pixi global install $pkg
    if ($LASTEXITCODE -ne 0) {
      echo "  Warning: Failed to install $pkg (exit code: $LASTEXITCODE)"
    }
  } catch {
    echo "  Warning: Failed to install $pkg - $($_.Exception.Message)"
  }
}

# Refresh PATH to include pixi global binaries
$env:Path = "$env:PIXI_HOME\bin;$env:Path"

# ---------------------------------------------------------------------------
# Download ITKPythonBuilds archive
# ---------------------------------------------------------------------------
$zipName        = "ITKPythonBuilds-windows.zip"
$zipDownloadUrl = "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/$ITK_PACKAGE_VERSION/$zipName"
$localZipName   = "ITKPythonBuilds-windows.zip"

if (Test-Path $localZipName) {
  echo "Found cached archive: $localZipName -- skipping download."
} else {
  echo "Downloading $zipDownloadUrl ..."

  # Try   first (faster, resumable), fall back to Invoke-WebRequest
  $aria2Path = Get-Command aria2c -ErrorAction SilentlyContinue
  if ($aria2Path) {
    echo "  Using aria2c for download..."
    & aria2c -c --file-allocation=none -s 10 -x 10 -o $localZipName $zipDownloadUrl
  } else {
    echo "  Using Invoke-WebRequest for download..."
    Invoke-WebRequest -Uri $zipDownloadUrl -OutFile $localZipName
  }
}

# Unpack archive
# Expected layout after extraction under $DASHBOARD_BUILD_DIRECTORY:
#   \ITK                          ITK source tree
#   \build\<cached-itk-build>     pre-built ITK artifacts
#   \IPP                          ITKPythonPackage scripts

echo "Extracting archive to $DASHBOARD_BUILD_DIRECTORY ..."
# Use 7-Zip to extract (matches the format it was created in)
$sevenZipPath = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path $sevenZipPath)) {
    Write-Error "7-Zip not found at $sevenZipPath. Please install 7-Zip."
    exit 1
}

& $sevenZipPath x $localZipName -o"$DASHBOARD_BUILD_DIRECTORY" -y
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to extract archive (exit code: $LASTEXITCODE)"
    exit 1
}
# Optional: overlay ITKPythonPackage build scripts from a specific tag
cd "$DASHBOARD_BUILD_DIRECTORY\IPP"
$env:PATH += ";C:\Program Files\Git\bin"
if ($ITKPYTHONPACKAGE_TAG) {
  echo "Updating build scripts to $ITKPYTHONPACKAGE_ORG/ITKPythonPackage@$ITKPYTHONPACKAGE_TAG"

  $ippTmpDir   = "$DASHBOARD_BUILD_DIRECTORY\IPP-tmp"
  $ippCloneUrl = "https://github.com/$ITKPYTHONPACKAGE_ORG/ITKPythonPackage.git"

  if (-not (Test-Path "$ippTmpDir\.git")) {
    echo "  Cloning repository..."
    & git clone $ippCloneUrl $ippTmpDir

    # Check if clone succeeded
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ippTmpDir)) {
      Write-Error "Failed to clone ITKPythonPackage repository"
      exit 1
    }
  }

  pushd $ippTmpDir
    echo "  Checking out $ITKPYTHONPACKAGE_TAG..."
    & git checkout $ITKPYTHONPACKAGE_TAG
    & git reset "origin/$ITKPYTHONPACKAGE_TAG" --hard
    & git status
  popd

  echo "  Copying updated scripts..."
  Copy-Item -Recurse -Force "$ippTmpDir\*" "$DASHBOARD_BUILD_DIRECTORY\IPP\"
  Remove-Item -Recurse -Force $ippTmpDir
}

# Build the module wheel
# Assemble paths used by build_wheels.py
$ippDir        = "$DASHBOARD_BUILD_DIRECTORY\IPP"
$buildScript   = "$ippDir\scripts\build_wheels.py"
# build_wheels.py expects the cached ITK build at <build-dir-root>\build\ITK-windows-py3XX-...
# Since the zip extracts directly into BDR (i.e. BDR\build\ITK-windows-py311-...), BDR is the root.
$buildDirRoot  = $DASHBOARD_BUILD_DIRECTORY
$itkSourceDir  = "$DASHBOARD_BUILD_DIRECTORY\ITK"
$moduleDepsDir = "$DASHBOARD_BUILD_DIRECTORY\MDEPS"

# Instead of building a string and using iex, build an argument array
$buildArgs = @(
  "run", "-e", $platformEnv,
  "python", $buildScript,
  "--platform-env", $platformEnv,
  "--module-source-dir", $MODULE_SRC_DIRECTORY,
  "--module-dependencies-root-dir", $moduleDepsDir
)

if ($env:ITK_MODULE_PREQ) {
    $buildArgs += @("--itk-module-deps", $env:ITK_MODULE_PREQ)
}

$buildArgs += @(
  "--no-build-itk-tarball-cache",
  "--build-dir-root", $buildDirRoot,
  "--itk-git-tag", $ITK_GIT_TAG,
  "--itk-source-dir", $itkSourceDir,
  "--itk-package-version", $ITK_PACKAGE_VERSION,
  "--no-use-ccache",
  "--skip-itk-build",
  "--skip-itk-wheel-build"
)

if ($setup_options.Length -gt 0) {
  $buildArgs += $setup_options.Split(" ")
}

if ($cmake_options.Length -gt 0) {
  $buildArgs += @("--")
  $buildArgs += $cmake_options.Split(" ")
}

echo "Building target module..."
& pixi @buildArgs
