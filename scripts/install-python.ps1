
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

Import-Module .\install-utils.ps1

$downloadDir = "D:/Downloads"

Download-URL 'https://www.python.org/ftp/python/2.7.12/python-2.7.12.amd64.msi' $downloadDir
Download-URL 'https://www.python.org/ftp/python/2.7.12/python-2.7.12.msi' $downloadDir

Install-MSI 'python-2.7.12.amd64.msi' $downloadDir 'C:\\Python27-x64'
Install-MSI 'python-2.7.12.msi' $downloadDir 'C:\\Python27-x86'

Download-URL 'https://www.python.org/ftp/python/3.5.2/python-3.5.2-amd64.exe' $downloadDir
Download-URL 'https://www.python.org/ftp/python/3.5.2/python-3.5.2.exe' $downloadDir

Install-Python 'python-3.5.2-amd64.exe' $downloadDir 'C:\\Python35-x64'
Install-Python 'python-3.5.2.exe' $downloadDir 'C:\\Python35-x86'


