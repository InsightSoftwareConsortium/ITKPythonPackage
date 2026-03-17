======================================
Build ITK Python packages
======================================

This section describes how to builds ITK's Python packages. In most cases, the
:ref:`pre-built ITK binary wheels can be used <quick-start>`.

ITK Python packages are built nightly on Kitware build systems and uploaded to
the `ITKPythonPackage GitHub releases page
<https://github.com/InsightSoftwareConsortium/ITKPythonPackage/releases>`_.


.. include:: Prerequisites.rst

Automated platform scripts
==========================

Steps required to build wheels on Linux, macOS and Windows have been
automated. The following sections outline how to use the associated scripts.


Setup Instructions
==================

1. Clone the ITKPythonPackage repository::

    $ git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git
    $ cd ITKPythonPackage

.. note::
   You can replace ``InsightSoftwareConsortium`` with a different organization if using a fork.

2. Configure the build environment (optional)

The following environment variables can be set to customize the build:

**MODULE_SRC_DIRECTORY**
    Directory where the ITK remote module is located. Default: Current Directory

**DASHBOARD_BUILD_DIRECTORY**
    Directory where build artifacts will be created. Default: /Users/svc-dashboard/D/P

**ITK_GIT_TAG**
    ITK version to build (branch name or commit hash). Default: ``main``

**ITK_PACKAGE_VERSION**
    ITK version tag to build against. Essentially the same as ITK_GIT_TAG for backwards compatability

**TARGET_ARCH**
    Target architecture. Default: ``x64`` (Linux), auto-detected (macOS)

**ITKPYTHONPACKAGE_ORG**
    GitHub organization hosting ITKPythonPackage. Default: ``InsightSoftwareConsortium``

**ITKPYTHONPACKAGE_TAG**
    Optional: specific tag/branch of build scripts to use. Default: ``main``

**MANYLINUX_VERSION** (manylinux only)
    Manylinux standard version. Default: ``_2_28``

**IMAGE_TAG** (Linux only)
    Docker image tag for manylinux builds. Default: ``20250913-6ea98ba``


For example::

    $ export ITK_GIT_TAG=v5.4.0
    $ export MANYLINUX_VERSION=_2_28


Building Wheels
===============

All build processes download pre-built ITK artifacts and builds wheels
using from the `ITKPythonBuilds repository <https://github.com/InsightSoftwareConsortium/ITKPythonBuilds>`_ distributions.

Linux
-----

You can download the Python builds for your specific system and architecture using the following script::

    $ ./scripts/dockcross-manylinux-download-cache.sh

On any linux distribution with docker and bash installed, running the script `dockcross-manylinux-build-wheels.sh` will create 64-bit wheels for python 3.9+ in the dist directory.::

    $ ./scripts/dockcross-manylinux-build-wheels.sh

Build for specific Python version(s)::

    $ ./scripts/dockcross-manylinux-build-wheels.sh cp310
    $ ./scripts/dockcross-manylinux-build-wheels.sh cp39 cp310 cp311

.. note::
   Python versions can be specified as ``cp39``, ``cp310``, ``cp311``, or
   ``py39``, ``py310``, ``py311`` - both formats are supported.

After the build completes, wheels will be located in the `DASHBOARD_BUILD_DIRECTORY` directory, for example::

    $ ls -1 ${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage-build/dist/
    itk-6.0.0-cp39-cp39-manylinux_2_28_x86_64.whl
    itk-6.0.0-cp310-cp310-manylinux_2_28_x86_64.whl
    itk-6.0.0-cp311-cp311-manylinux_2_28_x86_64.whl

macOS
-----

Build all default Python versions::

    $ ./scripts/macpython-download-cache-and-build-module-wheels.sh

Build for specific Python version(s)::

    $ ./scripts/macpython-download-cache-and-build-module-wheels.sh py310
    $ ./scripts/macpython-download-cache-and-build-module-wheels.sh py39 py310 py311


After the build completes, similarly, builds can be found in::

    $ ls -1 ${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage-build/dist/
    itk-6.0.0-cp39-cp39-macosx_10_9_x86_64.whl
    itk-6.0.0-cp310-cp310-macosx_10_9_x86_64.whl
    itk-6.0.0-cp311-cp311-macosx_10_9_x86_64.whl

Windows
-------

.. important::
   We need to work in a short directory to avoid path length limitations on
   Windows. The examples below use ``C:\IPP`` for this reason.

.. important::
   Disable antivirus checking on the build directory (e.g., ``C:\IPP``).
   The build system creates and deletes many files quickly, which can conflict
   with antivirus software and result in "Access Denied" errors. Windows
   Defender should be configured to exclude this directory.

Open a PowerShell terminal as Administrator, and install Python::

	PS C:\> Set-ExecutionPolicy Unrestricted
	PS C:\> $pythonArch = "64"
	PS C:\> iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))

In a PowerShell prompt, clone into a short path::

    PS C:\> cd C:\
    PS C:\> git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git IPP
    PS C:\> cd IPP

After the build completes::

    PS C:\IPP> ls dist
        Directory: C:\IPP\dist

        Mode                LastWriteTime         Length Name
        ----                -------------         ------ ----
        -a----         1/1/2026  11:14 PM       63274441 itk-6.0.0-cp39-cp39-win_amd64.whl
        -a----         1/1/2026  11:45 PM       63257220 itk-6.0.0-cp310-cp310-win_amd64.whl


Testing and Deployment
======================

Testing Wheels Locally
----------------------

Install and test a built wheel::

    $ pip install dist/itk-6.0.0-cp310-cp310-macosx_10_9_x86_64.whl
    $ python -c "import itk; print(dir(itk))"

Publishing Wheels
-----------------

Once you've built and tested the wheels, you can:

* Upload to PyPI using ``twine``::

    $ pip install twine
    $ twine upload dist/*.whl

* Upload to a private package index
* Distribute directly to users


Troubleshooting
===============

Path Length Issues (Windows)
-----------------------------

If you encounter path length errors:

* Use a shorter build directory (e.g., ``C:\IPP`` instead of ``C:\Users\YourName\Documents\Projects\ITKPythonPackage``)
* Enable long path support in Windows 10/11::

    PS C:\> New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force

Antivirus Conflicts (Windows)
------------------------------

Configure Windows Defender to exclude the build directory:

1. Open Windows Security
2. Go to "Virus & threat protection"
3. Under "Virus & threat protection settings", click "Manage settings"
4. Scroll to "Exclusions" and click "Add or remove exclusions"
5. Add the build directory (e.g., ``C:\IPP``)

.. Linux
.. -----

.. On any linux distribution with docker and bash installed, running the script dockcross-manylinux-build-wheels.sh will create 64-bit wheels for python 3.9+ in the dist directory.

.. For example::

..	$ git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git
..	[...]
..
..	$ ./scripts/dockcross-manylinux-build-wheels.sh
..	[...]

..	$ ls -1 dist/
..	itk-6.0.1.dev20251126-cp39-cp39m-manylinux2014_x86_64.whl
..	itk-6.0.1.dev20251126-cp39-cp39mu-manylinux2014_x86_64.whl
..	itk-6.0.1.dev20251126-cp39-cp39m-manylinux2014_x86_64.whl
..	itk-6.0.1.dev20251126-cp39-cp39m-manylinux2014_x86_64.whl
..	itk-6.0.1.dev20251126-cp39-cp39m-manylinux2014_x86_64.whl

.. macOS
.. -----

.. First, install the Python.org macOS Python distributions. This step requires sudo::

.. 	./scripts/macpython-install-python.sh


.. Then, build the wheels::

..	$ ./scripts/macpython-build-wheels.sh
..	[...]
..
..	$ ls -1 dist/
..	itk-6.0.1.dev20251126-cp39-cp39m-macosx_10_6_x86_64.whl
..	itk-6.0.1.dev20251126-cp39-cp39m-macosx_10_6_x86_64.whl
..	itk-6.0.1.dev20251126-cp39-cp39m-macosx_10_6_x86_64.whl
..	itk-6.0.1.dev20251126-cp39-cp39m-macosx_10_6_x86_64.whl

.. Windows
.. -------

.. First, install Microsoft Visual Studio 2015, Git, and CMake, which should be added to the system PATH environmental variable.

.. Open a PowerShell terminal as Administrator, and install Python::

..	PS C:\> Set-ExecutionPolicy Unrestricted
..	PS C:\> $pythonArch = "64"
..	PS C:\> iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))

.. In a PowerShell prompt::

..	PS C:\Windows> cd C:\
..	PS C:\> git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git IPP
..	PS C:\> cd IPP
..	PS C:\IPP> .\scripts\windows-build-wheels.ps1
..	[...]

..	PS C:\IPP> ls dist
..	    Directory: C:\IPP\dist


..	    Mode                LastWriteTime         Length Name
..	    ----                -------------         ------ ----
..	    -a----         4/9/2017  11:14 PM       63274441 itk-6.0.1.dev20251126-cp39-cp39m-win_amd64.whl
..	    -a----        4/10/2017   2:08 AM       63257220 itk-6.0.1.dev20251126-cp39-cp39m-win_amd64.whl

.. We need to work in a short directory to avoid path length limitations on
.. Windows, so the repository is cloned into C:\IPP.

.. Also, it is very important to disable antivirus checking on the C:\IPP
.. directory. Otherwise, the build system conflicts with the antivirus when many
.. files are created and deleted quickly, which can result in Access Denied
.. errors. Windows 10 ships with an antivirus application, Windows Defender, that
.. is enabled by default.

.. The below instructions are outdated and need to be re-written
.. sdist
.. -----
..
.. To create source distributions, sdist's, that will be used by pip to compile a wheel for installation if a binary wheel is not available for the current Python version or platform::
..
.. 	$ python -m build --sdist
.. 	[...]
..
.. 	$ ls -1 dist/
.. 	itk-6.0.1.dev20251126.tar.gz
.. 	itk-6.0.1.dev20251126.zip
..
.. Manual builds (not recommended)
.. ===============================
..
.. Building ITK Python wheels
.. --------------------------
..
.. Build the ITK Python wheel with the following command::
..
.. 	python3 -m venv build-itk
.. 	./build-itk/bin/pip install --upgrade pip
.. 	./build-itk/bin/pip install -r requirements-dev.txt
.. 	./build-itk/bin/python -m build
..
.. Build a wheel for a custom version of ITK
.. -----------------------------------------
..
.. To build a wheel for a custom version of ITK, point to your ITK git repository
.. with the `ITK_SOURCE_DIR` CMake variable::
..
..      ./build-itk/bin/python -m build --wheel -- \
.. 	  -DITK_SOURCE_DIR:PATH=/path/to/ITKPythonPackage-core-build/ITK
..
.. Other CMake variables can also be passed with `-D` after the double dash.
