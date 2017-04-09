Import-Module .\install-utils.ps1 -Force

$downloadDir = "C:/Downloads"

$version = "3.7.2"
$installDir = "C:/cmake-$version"

$archiveName = "cmake-$version-win64-x64"

if (![System.IO.Directory]::Exists($installDir)) {

  Download-URL "https://cmake.org/files/v3.7/$archiveName.zip" $downloadDir

  Extract-Zip (Join-Path $downloadDir "$archiveName.zip") "$installDir-tmp"

  $from = Join-Path "$installDir-tmp" $archiveName
  Write-Host "Moving $from to $installDir"
  Move-Item $from $installDir

  Write-Host "Removing $installDir-tmp"
  Remove-Item "$installDir-tmp"
}
