# Pulls build dependencies and build an ITK remote module.
#
# Variables to set before calling the script:
# - $env:ITK_PACKAGE_VERSION: Tag for ITKPythonBuilds build archive to use
# - $env:ITKPYTHONPACKAGE_TAG: Tag for ITKPythonPackage build scripts to use.
#     If ITKPYTHONPACKAGE_TAG is empty then the default scripts distributed
#     with the ITKPythonBuilds archive will be used.
# - $env:ITKPYTHONPACKAGE_ORG: Github organization or user to use for ITKPythonPackage
#     build script source. Default is InsightSoftwareConsortium.
#     Ignored if ITKPYTHONPACKAGE_TAG is empty.

trap { Write-Error $_; Exit 1 }
$AllProtocols = [System.Net.SecurityProtocolType]'Ssl3,Tls,Tls11,Tls12'
[System.Net.ServicePointManager]::SecurityProtocol = $AllProtocols

# Get ITKPythonBuilds archive with ITK build artifacts
set-alias sz "$env:ProgramFiles\7-Zip\7z.exe"
if (-not (Test-Path env:APPVEYOR)) {
  $pythonArch = "64"
  iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))
}
if (-not (Test-Path env:ITK_PACKAGE_VERSION)) { $env:ITK_PACKAGE_VERSION = 'v5.3.0' }
Invoke-WebRequest -Uri "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/$env:ITK_PACKAGE_VERSION/ITKPythonBuilds-windows.zip" -OutFile "ITKPythonBuilds-windows.zip"
sz x ITKPythonBuilds-windows.zip -oC:\P -aoa -r

# Optional: Update ITKPythonPackage build scripts
if ($env:ITKPYTHONPACKAGE_TAG) {
  if(!$env:ITKPYTHONPACKAGE_ORG) {
    $env:ITKPYTHONPACKAGE_ORG="InsightSoftwareConsortium"
  }

  echo "Updating build scripts to ($env:ITKPYTHONPACKAGE_ORG)/ITKPythonPackage@($env:ITKPYTHONPACKAGE_TAG)"

  pushd C:\P
  git clone "https://github.com/($env:ITKPYTHONPACKAGE_ORG)/ITKPythonPackage.git" "IPP-tmp"
  pushd "IPP-tmp"
  git checkout "($env:ITKPYTHONPACKAGE_TAG)"
  git status
  popd

  Remove-Item -Recurse -Force IPP/scripts/
  Copy-Item -Recurse IPP-tmp/scripts IPP/
  Remove-Item -Recurse -Force IPP-tmp/
  popd
}

# Get other build dependencies
Invoke-WebRequest -Uri "https://data.kitware.com/api/v1/file/5c0ad59d8d777f2179dd3e9c/download" -OutFile "doxygen-1.8.11.windows.bin.zip"
sz x doxygen-1.8.11.windows.bin.zip -oC:\P\doxygen -aoa -r
Invoke-WebRequest -Uri "https://data.kitware.com/api/v1/file/5bbf87ba8d777f06b91f27d6/download/grep-win.zip" -OutFile "grep-win.zip"
sz x grep-win.zip -oC:\P\grep -aoa -r
$env:Path += ";C:\P\grep"

# Run build scripts
C:\Python37-x64\python.exe C:\P\IPP\scripts\windows_build_module_wheels.py
