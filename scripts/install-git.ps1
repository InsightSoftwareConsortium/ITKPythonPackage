Import-Module .\install-utils.ps1

$downloadDir = "C:/Downloads"

$version = "2.12.0"
$archiveName = "Git-$version-64-bit.exe"

Download-URL "https://github.com/git-for-windows/git/releases/download/v$version.windows.1/$archiveName" $downloadDir

$installer = Join-Path $downloadDir $archiveName
Write-Host "Installing $installer"

Start-Process $installer -ArgumentList "/SP- /NORESTART /SUPPRESSMSGBOXES /SILENT /SAVEINF=`"$downloadDir\git-settings.txt`" /LOG=`"$downloadDir\git-installer.log`"" -NoNewWindow -PassThru -Wait
