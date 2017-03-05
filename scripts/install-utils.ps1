
function Always-Download-File {
param (
  [string]$url,
  [string]$file
  )
  If (Test-Path $file) {
    Remove-Item $file
  }
  Write-Host "Download $url"
  $downloader = new-object System.Net.WebClient
  $downloader.Headers.Add('User-Agent', 'Powershell'); # Setting agent avoids 403 forbidden error
  $downloader.DownloadFile($url, $file)
}

function Download-File {
param (
  [string]$url,
  [string]$file
  )
  if (![System.IO.File]::Exists($file)) {
    Always-Download-File $url $file
  }
}

function Download-URL {
param (
  [string]$url,
  [string]$downloadDir
  )
  if (![System.IO.Directory]::Exists($downloadDir)) {
    [System.IO.Directory]::CreateDirectory($downloadDir)
  }
  [uri]$url = $url
  $fileName = [System.IO.Path]::GetFileName($url.LocalPath)
  $destFilePath = Join-Path $downloadDir $fileName
  Download-File $url $destFilePath
}

function Install-MSI {
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
  Start-Process msiexec -ArgumentList "/a `"$filePath`" TARGETDIR=`"$targetDir`" ALLUSERS=1 /qb" -NoNewWindow -Wait
}

function Which {
param (
  [string]$progName
  )
  Get-Command "$progName" | Select-Object -ExpandProperty Definition
}

function Download-7zip {
param (
  [string]$downloadDir
  )
  Write-Host "Downloading 7za.exe commandline tool into $downloadDir"
  $7zaExe = Join-Path $downloadDir '7za.exe'
  Download-File 'https://github.com/chocolatey/chocolatey/blob/master/src/tools/7za.exe?raw=true' "$7zaExe"
  $7zaExe
}

function Always-Extract-Zip {
param (
  [string]$filePath,
  [string]$destDir
  )

  $7za = Download-7zip $downloadDir

  Write-Host "Found 7Zip [$7za]"
  Write-Host "Extracting $filePath to $destDir..."
  Start-Process "$7za" -ArgumentList "x -o`"$destDir`" -y `"$filePath`"" -NoNewWindow -PassThru -Wait
}

function Extract-Zip {
param (
  [string]$filePath,
  [string]$destDir
  )
  if (![System.IO.Directory]::Exists($destDir)) {
	Always-Extract-Zip $filePath $destDir
  }
}
