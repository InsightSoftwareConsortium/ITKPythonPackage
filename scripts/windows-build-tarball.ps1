# This script creates a tarball of the ITK Python package build tree. It is
# downloaded by the external module build scripts and used to build their
# Python package on GitHub CI services.

cd C:\P\
Remove-Item IPP\dist\*
C:\7-Zip\7z.exe a -t7z -r 'C:\P\ITKPythonBuilds-windows.zip' -w 'C:\P\IPP' 
# C:\7-Zip\7z.exe a -t7z -mx=9 -mfb=273 -ms -md=31 -myx=9 -mtm=- -mmt -mmtf -md=1536m -mmf=bt3 -mmc=10000 -mpb=0 -mlc=0 -r 'C:\P\ITKPythonBuilds-windows.zip' -w 'C:\P\IPP' 
