########################################################################
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
# - other parameters are passed to setup.py. If one of the parameters is "--",
#   the following parameters will be passed to cmake.
#     For instance, for Python 3.11, excluding nvcuda.dll during packaging
#     and setting RTK_USE_CUDA ON during configuration:
#
#     > windows-download-cache-and-build-module-wheels.ps1 11 --exclude-libs nvcuda.dll "--" -DRTK_USE_CUDA:BOOL=ON
#
#
# -----------------------------------------------------------------------
# Environment variables used in this script:
#
# `$env:ITK_PACKAGE_VERSION`: Tag for ITKPythonBuilds build archive to use
#
# `$env:ITKPYTHONPACKAGE_TAG`: Tag for ITKPythonPackage build scripts to use.
#     If ITKPYTHONPACKAGE_TAG is empty then the default scripts distributed
#     with the ITKPythonBuilds archive will be used.
#
# `$env:ITKPYTHONPACKAGE_ORG`: Github organization or user to use for ITKPythonPackage
#     build script source. Default is InsightSoftwareConsortium.
#     Ignored if ITKPYTHONPACKAGE_TAG is empty.
#
# `$env:ITK_MODULE_PREQ`: Delimited list of ITK module dependencies to build before building the target module.
#   Format is `<org_name>/<module_name>@<module_tag>:<org_name>/<module_name>@<module_tag>:...`.
#   For instance, `export ITK_MODULE_PREQ=InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0`
#
########################################################################

$pythonArch = "64"
$pythonVersion = "3.$($args[0])"
echo "Pulling Python $pythonVersion-x$pythonArch"
iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))

if (-not $env:ITK_PACKAGE_VERSION) { $env:ITK_PACKAGE_VERSION = 'v5.3.0' }
echo "Fetching build archive $env:ITK_PACKAGE_VERSION"
if (Test-Path C:\P) {
  Remove-Item -Recurse -Force C:\P
}
if (-not (Test-Path ITKPythonBuilds-windows.zip)) {
  Invoke-WebRequest -Uri "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/$env:ITK_PACKAGE_VERSION/ITKPythonBuilds-windows.zip" -OutFile "ITKPythonBuilds-windows.zip"
}
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
if (-not (Test-Path doxygen-1.8.11.windows.bin.zip)) {
  Invoke-WebRequest -Uri "https://data.kitware.com/api/v1/file/5c0ad59d8d777f2179dd3e9c/download" -OutFile "doxygen-1.8.11.windows.bin.zip"
}
7z x doxygen-1.8.11.windows.bin.zip -oC:\P\doxygen -aoa -r
if (-not (Test-Path grep-win.zip)) {
  Invoke-WebRequest -Uri "https://data.kitware.com/api/v1/file/5bbf87ba8d777f06b91f27d6/download/grep-win.zip" -OutFile "grep-win.zip"
}
7z x grep-win.zip -oC:\P\grep -aoa -r
$env:Path += ";C:\P\grep"

# Build ITK module dependencies, if any
$build_command = "& `"C:\Python$pythonVersion-x$pythonArch\python.exe`" `"C:\P\IPP\scripts\windows_build_module_wheels.py`" --no-cleanup --py-envs `"3$($args[0])-x64`""
foreach ($arg in $args[1..$args.length]) {
  if ($arg.substring(0,2) -eq "--") {
    $build_command = "$build_command $($arg)"
  }
  else {
    $build_command = "$build_command `"$($arg)`""
  }
}

echo "ITK_MODULE_PREQ: $env:ITK_MODULE_PREQ $ITK_MODULE_PREQ"
if ($env:ITK_MODULE_PREQ) {
  $MODULES_LIST = $env:ITK_MODULE_PREQ.split(":")
  foreach($MODULE_INFO in $MODULES_LIST) {
    $MODULE_ORG = $MODULE_INFO.split("/")[0]
    $MODULE_NAME = $MODULE_INFO.split("@")[0].split("/")[1]
    $MODULE_TAG = $MODULE_INFO.split("@")[1]

    $MODULE_UPSTREAM = "https://github.com/$MODULE_ORG/$MODULE_NAME.git"
    echo "Cloning from $MODULE_UPSTREAM"
    git clone $MODULE_UPSTREAM

    pushd $MODULE_NAME
    git checkout $MODULE_TAG
    echo "Building $MODULE_NAME"
    iex $build_command
    popd

    Copy-Item $MODULE_NAME/include/* include/
  }
}

# Run build scripts
iex $build_command
