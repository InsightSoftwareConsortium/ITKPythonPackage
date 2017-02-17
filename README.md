# ITKPythonPackage

This project provides a `setup.py` script that build ITK Python
[wheels](https://www.python.org/dev/peps/pep-0427/).
[ITK](https://itk.org) is an open-source,
cross-platform system that provides developers with an extensive suite
of software tools for image analysis.

The Python packages are build nightly. To install the ITK Python package:

```bash
python -m pip install --upgrade pip
python -m pip install itk -f https://github.com/InsightSoftwareConsortium/ITKPythonPackage/releases/tag/nightly
```

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
ITK-0.11.0-cp27-cp27m-manylinux1_x86_64.whl
ITK-0.11.0-cp27-cp27mu-manylinux1_x86_64.whl
ITK-0.11.0-cp33-cp33m-manylinux1_x86_64.whl
ITK-0.11.0-cp34-cp34m-manylinux1_x86_64.whl
ITK-0.11.0-cp35-cp35m-manylinux1_x86_64.whl
ITK-0.11.0-cp36-cp36m-manylinux1_x86_64.whl
```

### MacOSX

First install the Python.org MacOSX Python's. This step requires `sudo`:

```bash
./scripts/macpython-install-python.sh
```

Then, build the wheels:

```
$ ./scripts/macpython-build-wheels.sh
[...]

$ ls -1 dist/
itk-4.11.0.dev20170213-cp27-cp27m-macosx_10_6_x86_64.whl
itk-4.11.0.dev20170213-cp34-cp34m-macosx_10_6_x86_64.whl
itk-4.11.0.dev20170213-cp35-cp35m-macosx_10_6_x86_64.whl
itk-4.11.0.dev20170213-cp36-cp36m-macosx_10_6_x86_64.whl
```

### Windows

*To be documented*

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

