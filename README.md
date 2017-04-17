# ITKPythonPackage

This project provides a `setup.py` script that build ITK Python
[wheels](https://www.python.org/dev/peps/pep-0427/).
[ITK](https://itk.org) is an open-source,
cross-platform system that provides developers with an extensive suite
of software tools for image analysis.

The Python packages are built daily. To install the ITK Python package:

```bash
python -m pip install --upgrade pip
python -m pip install itk -f https://github.com/InsightSoftwareConsortium/ITKPythonPackage/releases/tag/latest
```

For more information on ITK's Python wrapping, see an [introduction in the ITK
Software
Guide](https://itk.org/ITKSoftwareGuide/html/Book1/ITKSoftwareGuide-Book1ch3.html#x32-420003.7).
There are also many [downloadable
examples](https://itk.org/ITKExamples/search.html?q=Python) documented in Sphinx.

## Automated wheels building with scripts

Steps required to build wheels on Linux, MacOSX and Windows have been automated. The
following sections outline how to use the associated scripts.

### Linux

On any linux distribution with `docker` and `bash` installed, running the script
`dockcross-manylinux-build-wheels.sh` will create 64-bit wheels for both
python 2.x and python 3.x in the `dist` directory.

For example:

```bash
$ git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git
[...]

$ ./scripts/dockcross-manylinux-build-wheels.sh
[...]

$ ls -1 dist/
itk-4.11.0.dev20170218-cp27-cp27m-manylinux1_x86_64.whl
itk-4.11.0.dev20170218-cp27-cp27mu-manylinux1_x86_64.whl
itk-4.11.0.dev20170218-cp34-cp34m-manylinux1_x86_64.whl
itk-4.11.0.dev20170218-cp35-cp35m-manylinux1_x86_64.whl
itk-4.11.0.dev20170218-cp36-cp36m-manylinux1_x86_64.whl
```

### MacOSX

First install the Python.org MacOSX Python's. This step requires `sudo`:

```bash
./scripts/macpython-install-python.sh
```

Then, build the wheels:

```bash
$ ./scripts/macpython-build-wheels.sh
[...]

$ ls -1 dist/
itk-4.11.0.dev20170213-cp27-cp27m-macosx_10_6_x86_64.whl
itk-4.11.0.dev20170213-cp34-cp34m-macosx_10_6_x86_64.whl
itk-4.11.0.dev20170213-cp35-cp35m-macosx_10_6_x86_64.whl
itk-4.11.0.dev20170213-cp36-cp36m-macosx_10_6_x86_64.whl
```

### Windows

First, install [Microsoft Visual C++ Compiler for Python
2.7](http://aka.ms/vcpython27), [Visual Studio
2015](https://www.visualstudio.com/downloads/),
[Git](https://git-scm.com/download/win), and [CMake](https://cmake.org/download/), which should be added to the system `PATH` environmental variable.

Open a PowerShell terminal as Administrator, and install Python:

```powershell
PS C:\> Set-ExecutionPolicy Unrestricted
PS C:\> iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))
```


In a PowerShell prompt:

```powershell
PS C:\Windows> cd C:\
PS C:\> git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git IPP
PS C:\> cd IPP
PS C:\IPP> .\scripts\windows-build-wheels.ps1
[...]

PS C:\IPP> ls dist
    Directory: C:\IPP\dist


    Mode                LastWriteTime         Length Name
    ----                -------------         ------ ----
    -a----         4/9/2017   5:21 PM       59435508 itk-4.11.0.dev20170407-cp27-cp27m-win_amd64.whl
    -a----         4/9/2017  11:14 PM       63274441 itk-4.11.0.dev20170407-cp35-cp35m-win_amd64.whl
    -a----        4/10/2017   2:08 AM       63257220 itk-4.11.0.dev20170407-cp36-cp36m-win_amd64.whl

```

We need to work in a short directory to avoid path length limitations on
Windows, so the repository is cloned into `C:\IPP`. Also, it is *very important
to disable antivirus* checking on the `C:\IPP` directory. Otherwise, the build
system conflicts with the antivirus when many files are created and deleted
quickly, which can result in Access Denied errors. Windows 10 ships with an
antivirus application, Windows Defender, that is enabled by default.

### sdist

To create source distributions,
[sdist](https://docs.python.org/3.6/distutils/sourcedist.html)'s,  that will
be used by pip to compile a wheel for installation if a binary wheel is not
available for the current Python version or platform:

```bash
$ python setup.py sdist --formats=gztar,zip
[...]

$ ls -1 dist/
itk-4.11.0.dev20170216.tar.gz
itk-4.11.0.dev20170216.zip
```


## Prerequisites

Building wheels requires:
* [CMake](https://cmake.org)
* Git
* C++ Compiler - Platform specific requirements are summarized in [scikit-build documentation](http://scikit-build.readthedocs.io).
* Python

## Detailed build instructions

### Building ITK Python wheels

Build the ITK Python wheel with the following command:

```
mkvirtualenv build-itk
pip install -r requirements-dev.txt
python setup.py bdist_wheel
```

### Efficiently building wheels for different version of python

If on a given platform you would like to build wheels for different version of python, you can download and build
the ITK components independent from python first and reuse them when building each wheel.

Here are the steps:

1. Build `ITKPythonPackage` with `ITKPythonPackage_BUILD_PYTHON` set to `OFF`

2. Build "flavor" of package using:

```
python setup.py bdist_wheel -- \
  -DITK_SOURCE_DIR:PATH=/path/to/ITKPythonPackage-core-build/ITK-source
```

## Miscellaneous

Written by Jean-Christophe Fillion-Robin and Matt McCormick from Kitware Inc.

It is covered by the Apache License, Version 2.0:

http://www.apache.org/licenses/LICENSE-2.0

For more information about ITK, visit http://itk.org

