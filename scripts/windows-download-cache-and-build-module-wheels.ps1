trap { Write-Error $_; Exit 1 }

set-alias sz "$env:ProgramFiles\7-Zip\7z.exe"  
iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))
Invoke-WebRequest -Uri "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/v4.12.0.post1/ITKPythonBuilds-windows.zip" -OutFile "ITKPythonBuilds-windows.zip"
sz x ITKPythonBuilds-windows.zip -oC:\P -aoa -r
C:\Python27-x64\python.exe C:\P\IPP\scripts\windows_build_module_wheels.py
