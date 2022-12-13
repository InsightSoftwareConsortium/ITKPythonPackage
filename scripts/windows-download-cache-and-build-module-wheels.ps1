# -----------------------------------------------------------------------
# Pull build dependencies and build an ITK external module.
#
# This script must be run in an x64 Developer Powershell.
# See https://learn.microsoft.com/en-us/visualstudio/ide/reference/command-prompt-powershell?view=vs-2022#developer-powershell
#
# -----------------------------------------------------------------------
# Positional parameters:
# - 0th parameter: Python minor version.
#     For instance, for Python 3.11:
#
#     > windows-download-cache-and-build-module-wheels.ps1 11
#
# -----------------------------------------------------------------------
# Environment variables used in this script:
#
# - $env:ITK_PACKAGE_VERSION: Tag for ITKPythonBuilds build archive to use
# - $env:ITKPYTHONPACKAGE_TAG: Tag for ITKPythonPackage build scripts to use.
#     If ITKPYTHONPACKAGE_TAG is empty then the default scripts distributed
#     with the ITKPythonBuilds archive will be used.
# - $env:ITKPYTHONPACKAGE_ORG: Github organization or user to use for ITKPythonPackage
#     build script source. Default is InsightSoftwareConsortium.
#     Ignored if ITKPYTHONPACKAGE_TAG is empty.
#

$pythonArch = "64"
$pythonVersion = "3.$($args[0])"
echo "Pulling Python $pythonVersion-x$pythonArch"
iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))

if (-not $env:ITK_PACKAGE_VERSION) { $env:ITK_PACKAGE_VERSION = 'v5.3.0' }
echo "Fetching build archive $env:ITK_PACKAGE_VERSION"
Invoke-WebRequest -Uri "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/$env:ITK_PACKAGE_VERSION/ITKPythonBuilds-windows.zip" -OutFile "ITKPythonBuilds-windows.zip"
7z x ITKPythonBuilds-windows.zip -oC:\P -aoa -r

# Optional: Update ITKPythonPackage build scripts
if ($env:ITKPYTHONPACKAGE_TAG) {
  if(-not $env:ITKPYTHONPACKAGE_ORG) {
    $env:ITKPYTHONPACKAGE_ORG="InsightSoftwareConsortium"
  }

  echo "Updating build scripts to $env:ITKPYTHONPACKAGE_ORG/ITKPythonPackage@$env:ITKPYTHONPACKAGE_TAG"

  pushd C:\P
  git clone "https://github.com/$env:ITKPYTHONPACKAGE_ORG/ITKPythonPackage.git" "IPP-tmp"
  pushd "IPP-tmp"
  git checkout "$env:ITKPYTHONPACKAGE_TAG"
  git status
  popd

  Remove-Item -Recurse -Force IPP/scripts/
  Copy-Item -Recurse IPP-tmp/scripts IPP/
  Copy-Item IPP-tmp/requirements-dev.txt IPP/
  Remove-Item -Recurse -Force IPP-tmp/
  popd
}

# Get other build dependencies
Invoke-WebRequest -Uri "https://data.kitware.com/api/v1/file/5c0ad59d8d777f2179dd3e9c/download" -OutFile "doxygen-1.8.11.windows.bin.zip"
7z x doxygen-1.8.11.windows.bin.zip -oC:\P\doxygen -aoa -r
Invoke-WebRequest -Uri "https://data.kitware.com/api/v1/file/5bbf87ba8d777f06b91f27d6/download/grep-win.zip" -OutFile "grep-win.zip"
7z x grep-win.zip -oC:\P\grep -aoa -r
$env:Path += ";C:\P\grep"

# Run build scripts
& "C:\Python$pythonVersion-x$pythonArch\python.exe" C:\P\IPP\scripts\windows_build_module_wheels.py --no-cleanup --py-envs "3$($args[0])-x64"
