
#
# See https://pip.pypa.io/en/stable/installing/
#

function Install-Pip {
param (
  [string]$pythonDir,
  [string]$downloadDir
  )
  Download-URL 'https://bootstrap.pypa.io/get-pip.py' $downloadDir
  
  $get_pip_script = Join-Path $downloadDir "get-pip.py"

  $interpreter = Join-Path $pythonDir "python.exe"
  Write-Host "Installing pip into $interpreter"
  
  Start-Process $interpreter -ArgumentList "`"$get_pip_script`"" -NoNewWindow -Wait
}

function Pip-Install {
param (
  [string]$pythonDir,
  [string]$package
  )
  
  $pip = Join-Path $pythonDir "Scripts\\pip.exe"
  
  Write-Host "Installing $package using $pip"
  
  Start-Process $pip -ArgumentList "install `"$package`"" -NoNewWindow -Wait
}

Import-Module .\install-utils.ps1


$downloadDir = "D:/Downloads"

Install-Pip 'C:\\Python27-x86' $downloadDir
Install-Pip 'C:\\Python27-x64' $downloadDir
Install-Pip 'C:\\Python35-x86' $downloadDir
Install-Pip 'C:\\Python35-x64' $downloadDir

Pip-Install 'C:\\Python27-x86' 'virtualenv'
Pip-Install 'C:\\Python27-x64' 'virtualenv'
Pip-Install 'C:\\Python35-x86' 'virtualenv'
Pip-Install 'C:\\Python35-x64' 'virtualenv'
