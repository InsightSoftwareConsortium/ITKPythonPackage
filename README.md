# ITK Python Package

This project provides a `setup.py` script to build ITK Python binary
packages and infrastructure to build ITK external module Python
packages.

The Insight Toolkit (ITK) is an open-source, cross-platform system that provides developers
with an extensive suite of software tools for image analysis.
More information is available on the [ITK website](https://itk.org/)
or at the [ITK GitHub homepage](https://github.com/insightSoftwareConsortium/ITK).

## Table of Contents

- [Using ITK Python Packages](#using-itk-python-packages)
- [Building with ITKPythonPackage](#building-with-itkpythonpackage)
- [Frequently Asked Questions](#frequently-asked-questions)
- [Additional Information](#additional-information)

## Using ITK Python Packages

ITKPythonPackage scripts can be used to produce [Python](https://www.python.org/) packages
for ITK and ITK external modules. The resulting packages can be
hosted on the [Python Package Index (PyPI)](https://pypi.org/)
for easy distribution.

### Installation

To install baseline ITK Python packages:

```sh
> pip install itk
```

To install ITK external module packages:

```sh
> pip install itk-<module_name>
```

### Using ITK in Python scripts

```python
    import itk
    import sys

    input_filename = sys.argv[1]
    output_filename = sys.argv[2]

    image = itk.imread(input_filename)

    median = itk.median_image_filter(image, radius=2)

    itk.imwrite(median, output_filename)
```

### Other Resources for Using ITK in Python

See also the [ITK Python Quick Start
Guide](https://itkpythonpackage.readthedocs.io/en/master/Quick_start_guide.html).
There are also many [downloadable examples on the ITK examples website](https://examples.itk.org/search.html?q=Python).

For more information on ITK's Python wrapping, [an introduction is
provided in the ITK Software
Guide](https://itk.org/ITKSoftwareGuide/html/Book1/ITKSoftwareGuide-Book1ch3.html#x32-420003.7).

## Building with ITKPythonPackage

ITK reusable workflows are available to build and package Python wheels as
part of Continuous Integration (CI) via Github Actions runners.
Those workflows can handle the overhead of fetching, configuring, and
running ITKPythonPackage build scripts for most ITK external modules.
See [ITKRemoteModuleBuildTestPackageAction](https://github.com/InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction)
for more information.

For special cases where ITK reusable workflows are not a good fit,
ITKPythonPackage scripts can be directly used to build Python wheels
to target Windows, Linux, and MacOS platforms. See
[ITKPythonPackage ReadTheDocs](https://itkpythonpackage.readthedocs.io/en/master/Build_ITK_Module_Python_packages.html)
documentation for more information on building wheels by hand.

## Frequently Asked Questions

### What target platforms and architectures are supported?

ITKPythonPackage currently supports building wheels for the following platforms and architectures:
- Windows 10 x86_64 platforms
- Windows 11 x86_64 platforms
- MacOS 10.9+ x86_64 platforms
- MacOS 11.0+ arm64 platforms
- Linux glibc 2.17+ (E.g. Ubuntu 18.04+) x86_64 platforms
- Linux glibc 2.28+ (E.g. Ubuntu 20.04+) aarch64 (ARMv8) platforms

### What should I do if my target platform/architecture does not appear on the list above?

Please open an issue in the [ITKPythonPackage issue tracker](https://github.com/InsightSoftwareConsortium/ITKPythonPackage/issues)
for discussion, and consider contributing either time or funding to support
development. The ITK open source ecosystem is driven through contributions from its community members.

### What is an ITK external module?

The Insight Toolkit consists of several baseline module groups for image analysis
including filtering, I/O, registration, segmentation, and more. Community members
can extend ITK by developing an ITK "external" module which stands alone in a separate
repository and its independently built and tested. An ITK external module which
meets community standards for documentation and maintenance may be included in the
ITK build process as an ITK "remote" module to make it easier to retrieve and build.

Visit [ITKModuleTemplate](https://github.com/insightSoftwareConsortium/ITKmoduletemplate)
to get started creating a new ITK external module.

### How can I make my ITK C++ filters available in Python?

ITK uses SWIG to wrap C++ filters for use in Python.
See [Chapter 9 in the ITK Software Guide](https://itk.org/ITKSoftwareGuide/html/Book1/ITKSoftwareGuide-Book1ch9.html)
or visit [ITKModuleTemplate](https://github.com/insightSoftwareConsortium/ITKmoduletemplate)
to get started on writing `.wrap` files.

After you've added wrappings for your external module C++ filters
you may build and distribute Python packages automatically with
[ITKRemoteModuleBuildTestPackageAction](https://github.com/InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction)
or manually with ITKPythonPackage scripts.

### What makes building ITK external module wheels different from building ITK wheels?

In order to build an ITK external module you must have first built ITK for the same target platform.
However, building ITK modules and wrapping them for Python can take a very long time!
To avoid having to rebuild ITK before building every individual external module,
artifacts from the ITK build process (headers, source files, wrapper outputs, and more) are
packaged and cached as [ITKPythonBuilds](https://github.com/insightSoftwareConsortium/ITKpythonbuilds)
releases.

In order to build Python wheels for an ITK external module, ITKPythonPackage scripts
first fetch the appropriate ITK Python build artifacts along with other necessary
tools. Then, the module can be built, packaged, and distributed on [PyPI](https://pypi.org/).

### My external module has a complicated build process. Is it supported by ITKPythonPackage?

Start by consulting the [ITKPythonPackage ReadTheDocs](https://itkpythonpackage.readthedocs.io/en/master/Build_ITK_Module_Python_packages.html)
documentation and the [ITKPythonPackage issue tracker](https://github.com/InsightSoftwareConsortium/ITKPythonPackage/issues)
for discussion related to your specific issue.

If you aren't able to find an answer for your specific case, please start a discussion the
[ITK Discourse forum](https://discourse.itk.org/) for help.

## Additional Information

-   Free software: Apache Software license
-   Documentation: <http://itkpythonpackage.readthedocs.org>
-   Source code: <https://github.com/InsightSoftwareConsortium/ITKPythonPackage>
