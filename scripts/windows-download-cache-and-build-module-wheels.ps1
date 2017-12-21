trap { Write-Error $_; Exit 1 }

set-alias sz "$env:ProgramFiles\7-Zip\7z.exe"  
iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))
Invoke-WebRequest -Uri "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/v4.13.0/ITKPythonBuilds-windows.zip" -OutFile "ITKPythonBuilds-windows.zip"
sz x ITKPythonBuilds-windows.zip -oC:\P -aoa -r
Invoke-WebRequest -Uri "http://ftp.stack.nl/pub/users/dimitri/doxygen-1.8.11.windows.bin.zip" -OutFile "doxygen-1.8.11.windows.bin.zip"
sz x doxygen-1.8.11.windows.bin.zip -oC:\P\doxygen -aoa -r
C:\Python27-x64\python.exe C:\P\IPP\scripts\windows_build_module_wheels.py
