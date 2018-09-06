# This script creates a tarball of the ITK Python package build tree. It is
# downloaded by the external module build scripts and used to build their
# Python package on GitHub CI services.

cd C:\P\
Remove-Item IPP\dist\*
C:\7-Zip\7z.exe a -r 'C:\P\ITKPythonBuilds-windows.zip' -w 'C:\P\IPP' -mem=AES256
