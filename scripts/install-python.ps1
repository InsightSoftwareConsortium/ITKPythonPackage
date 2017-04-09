Import-Module .\install-utils.ps1 -Force

function Install-Python {
param (
  [string]$fileName,
  [string]$downloadDir,
  [string]$targetDir
  )

  Write-Host "Installing $fileName into $targetDir"
  if ([System.IO.Directory]::Exists($targetDir)) {
    Write-Host "-> skipping: existing target directory"
	return
  }
  if (![System.IO.Directory]::Exists($targetDir)) {
    [System.IO.Directory]::CreateDirectory($targetDir)
  }
  $filePath = Join-Path $downloadDir $fileName
  Start-Process $filePath -ArgumentList "TargetDir=$targetDir InstallAllUsers=1 Include_launcher=0 PrependPath=0 Shortcuts=0 /passive" -NoNewWindow -Wait
}

# See https://pip.pypa.io/en/stable/installing/
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

$downloadDir = "C:/Downloads"

Download-URL 'https://www.python.org/ftp/python/2.7.12/python-2.7.12.amd64.msi' $downloadDir
Download-URL 'https://www.python.org/ftp/python/2.7.12/python-2.7.12.msi' $downloadDir

Install-MSI 'python-2.7.12.amd64.msi' $downloadDir 'C:\\Python27-x64'
Install-MSI 'python-2.7.12.msi' $downloadDir 'C:\\Python27-x86'

Install-Pip 'C:\\Python27-x86' $downloadDir
Install-Pip 'C:\\Python27-x64' $downloadDir

Pip-Install 'C:\\Python27-x86' 'virtualenv'
Pip-Install 'C:\\Python27-x64' 'virtualenv'


$exeVersions = @("3.5.3", "3.6.0")
foreach ($version in $exeVersions) {
  $split = $version.Split(".")
  $majorMinor = [string]::Join("", $split, 0, 2)
  Download-URL "https://www.python.org/ftp/python/$($version)/python-$($version)-amd64.exe" $downloadDir
  Download-URL "https://www.python.org/ftp/python/$($version)/python-$($version).exe" $downloadDir

  Install-Python "python-$($version)-amd64.exe" $downloadDir "C:\\Python$($majorMinor)-x64"
  Install-Python "python-$($version).exe" $downloadDir "C:\\Python$($majorMinor)-x86"

  Install-Pip "C:\\Python$($majorMinor)-x86" $downloadDir
  Install-Pip "C:\\Python$($majorMinor)-x64" $downloadDir

  Pip-Install "C:\\Python$($majorMinor)-x86" 'virtualenv'
  Pip-Install "C:\\Python$($majorMinor)-x64" 'virtualenv'
}

