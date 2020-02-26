trap { Write-Error $_; Exit 1 }
$AllProtocols = [System.Net.SecurityProtocolType]'Ssl3,Tls,Tls11,Tls12'
[System.Net.ServicePointManager]::SecurityProtocol = $AllProtocols

set-alias sz "$env:ProgramFiles\7-Zip\7z.exe"
if (-not (Test-Path env:APPVEYOR)) {
  $pythonArch = "64"
  iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))
}
if (-not (Test-Path env:ITK_PACKAGE_VERSION)) { $env:ITK_PACKAGE_VERSION = 'v5.1rc02' }
Invoke-WebRequest -Uri "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/$env:ITK_PACKAGE_VERSION/ITKPythonBuilds-windows.zip" -OutFile "ITKPythonBuilds-windows.zip"
sz x ITKPythonBuilds-windows.zip -oC:\P -aoa -r
Invoke-WebRequest -Uri "https://data.kitware.com/api/v1/file/5c0ad59d8d777f2179dd3e9c/download" -OutFile "doxygen-1.8.11.windows.bin.zip"
sz x doxygen-1.8.11.windows.bin.zip -oC:\P\doxygen -aoa -r
Invoke-WebRequest -Uri "https://data.kitware.com/api/v1/file/5bbf87ba8d777f06b91f27d6/download/grep-win.zip" -OutFile "grep-win.zip"
sz x grep-win.zip -oC:\P\grep -aoa -r
$env:Path += ";C:\P\grep"
C:\Python35-x64\python.exe C:\P\IPP\scripts\windows_build_module_wheels.py
