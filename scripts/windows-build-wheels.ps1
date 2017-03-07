
$scriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
$rootDir = Resolve-Path "$scriptDir\\.."

function Pip-Install {
param (
  [string]$pythonDir,
  [string]$package
  )

  $pip = Join-Path $pythonDir "Scripts\\pip.exe"

  Write-Host "Installing $package using $pip"

  Start-Process $pip -ArgumentList "install `"$package`"" -NoNewWindow -Wait
}

function Prepare-Build-Env {
param (
  [string]$pythonVersion
  )
  $pythonDir = "C:\\Python$pythonVersion"
  If (![System.IO.Directory]::Exists($pythonDir)) {
    Write-Host "Aborting. pythonDir [$pythonDir] does not exist."
    return
  }
  $venv = Join-Path $pythonDir "Scripts\\virtualenv.exe"
  $venvDir = Join-Path $rootDir "venv-$pythonVersion"
  If (![System.IO.Directory]::Exists($venvDir)) {
    Start-Process $venv -ArgumentList "$venvDir" -NoNewWindow -Wait
  }

  Pip-Install "$venvDir" "cmake"
  Pip-Install "$venvDir" "ninja"
  Pip-Install "$venvDir" "scikit-build"
}

function Build-Wheel {
param (
  [string]$pythonVersion
  )

  $venvDir = Join-Path $rootDir "venv-$pythonVersion"

  $PYTHON_EXECUTABLE = Join-Path $venvDir "Scripts\\python.exe"
  $PYTHON_INCLUDE_DIR = Join-Path $venvDir "Include"
  # XXX It should be possible to query skbuild for the library dir associated
  #     with a given interpreter.
  $xy_ver = $pythonVersion.split("-")[0]
  $PYTHON_LIBRARY = "C:\\Python$pythonVersion\\libs\\python$xy_ver.lib"

  Write-Host ""
  Write-Host "PYTHON_EXECUTABLE:${PYTHON_EXECUTABLE}"
  Write-Host "PYTHON_INCLUDE_DIR:${PYTHON_INCLUDE_DIR}"
  Write-Host "PYTHON_LIBRARY:${PYTHON_LIBRARY}"

  $pip = Join-Path $venvDir "Scripts\\pip.exe"

  # Update PATH
  $old_path = $env:PATH
  $env:PATH = "$venvDir\\Scripts;$env:PATH"

  Start-Process $pip -ArgumentList "install -r $rootDir\\requirements-dev.txt" -NoNewWindow -Wait

  Start-Process $PYTHON_EXECUTABLE -ArgumentList "setup.py bdist_wheel --build-type MinSizeRel -G Ninja -- -DCMAKE_MAKE_PROGRAM:FILEPATH=$NINJA_EXECUTABLE -DITK_SOURCE_DIR:PATH=$standaloneDir\\ITK-source -DPYTHON_EXECUTABLE:FILEPATH=$PYTHON_EXECUTABLE -DPYTHON_INCLUDE_DIR:PATH=$PYTHON_INCLUDE_DIR -DPYTHON_LIBRARY:FILEPATH=$PYTHON_LIBRARY" -NoNewWindow -Wait

  Start-Process $PYTHON_EXECUTABLE -ArgumentList "setup.py clean" -NoNewWindow -Wait

  # Restore PATH
  $env:PATH = $old_path
}

Prepare-Build-Env "27-x64"
Prepare-Build-Env "35-x64"

$standaloneDir = Join-Path $rootDir "standalone-build"
if (![System.IO.Directory]::Exists($standaloneDir)) {
  [System.IO.Directory]::CreateDirectory($standaloneDir)
}
Pushd $standaloneDir
  $CMAKE_EXECUTABLE = Join-Path $rootDir "venv-27-x64\Scripts\cmake.exe"
  $NINJA_EXECUTABLE = Join-Path $rootDir "venv-27-x64\Scripts\ninja.exe"
  Start-Process $CMAKE_EXECUTABLE -ArgumentList `
    "-DITKPythonPackage_BUILD_PYTHON:PATH=0 `
	-G Ninja `
	-DCMAKE_MAKE_PROGRAM:FILEPATH=$NINJA_EXECUTABLE $rootDir" -NoNewWindow -Wait

  Start-Process $NINJA_EXECUTABLE -NoNewWindow -Wait
Popd


# Compile wheels re-using standalone project and archive cache
Build-Wheel "27-x64"
Build-Wheel "35-x64"

