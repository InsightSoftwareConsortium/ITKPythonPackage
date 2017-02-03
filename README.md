# ITKPythonPackage

This project provides a `setup.py` script that build ITK Python wheel. [ITK](http://www.itk.org) is an open-source,
cross-platform system that provides developers with an extensive suite of software tools for image analysis.

## Automated wheels building with scripts

Steps required to build wheels on Linux, MacOSX and Windows have been automated. The
following sections outline how to use the associated scripts.

### Linux

On any linux distribution with `docker` and `bash` installed, running the script
`dockcross-manylinux-build-wheels.sh` will create 64-bit wheels for both
python 2.x and python 3.x in the `dist` directory.

For example:

```bash
$ git clone git://github.com/InsightSoftwareConsortium/ITKPythonPackage.git
[...]

$ ./scripts/dockcross-manylinux-build-wheels.sh
[...]

$ ls -1 dist/
# To be updated
```

### MacOSX

*To be documented*

### Windows

*To be documented*

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

## Miscellaneous

Written by Jean-Christophe Fillion-Robin and Matt McCormick from Kitware Inc.

It is covered by the Apache License, Version 2.0:

http://www.apache.org/licenses/LICENSE-2.0

For more information about ITK, visit http://itk.org

