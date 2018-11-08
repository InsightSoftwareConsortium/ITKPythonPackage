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

Linux
-----

On any linux distribution with docker and bash installed, running the script dockcross-manylinux-build-wheels.sh will create 64-bit wheels for both python 2.x and python 3.x in the dist directory.

For example::

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

macOS
-----

First, install the Python.org macOS Python distributions. This step requires sudo::

	./scripts/macpython-install-python.sh


Then, build the wheels::

	$ ./scripts/macpython-build-wheels.sh
	[...]

	$ ls -1 dist/
	itk-4.11.0.dev20170213-cp27-cp27m-macosx_10_6_x86_64.whl
	itk-4.11.0.dev20170213-cp34-cp34m-macosx_10_6_x86_64.whl
	itk-4.11.0.dev20170213-cp35-cp35m-macosx_10_6_x86_64.whl
	itk-4.11.0.dev20170213-cp36-cp36m-macosx_10_6_x86_64.whl

Windows
-------

First, install Microsoft Visual Studio 2015, Git, and CMake, which should be added to the system PATH environmental variable.

Open a PowerShell terminal as Administrator, and install Python::

	PS C:\> Set-ExecutionPolicy Unrestricted
	PS C:\> iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/scikit-build/scikit-ci-addons/master/windows/install-python.ps1'))

In a PowerShell prompt::

	PS C:\Windows> cd C:\
	PS C:\> git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git IPP
	PS C:\> cd IPP
	PS C:\IPP> .\scripts\windows-build-wheels.ps1
	[...]

	PS C:\IPP> ls dist
	    Directory: C:\IPP\dist


	    Mode                LastWriteTime         Length Name
	    ----                -------------         ------ ----
	    -a----         4/9/2017  11:14 PM       63274441 itk-4.11.0.dev20170407-cp35-cp35m-win_amd64.whl
	    -a----        4/10/2017   2:08 AM       63257220 itk-4.11.0.dev20170407-cp36-cp36m-win_amd64.whl

We need to work in a short directory to avoid path length limitations on
Windows, so the repository is cloned into C:\IPP.

Also, it is very important to disable antivirus checking on the C:\IPP
directory. Otherwise, the build system conflicts with the antivirus when many
files are created and deleted quickly, which can result in Access Denied
errors. Windows 10 ships with an antivirus application, Windows Defender, that
is enabled by default.

sdist
-----

To create source distributions, sdist's, that will be used by pip to compile a wheel for installation if a binary wheel is not available for the current Python version or platform::

	$ python setup.py sdist --formats=gztar,zip
	[...]

	$ ls -1 dist/
	itk-4.11.0.dev20170216.tar.gz
	itk-4.11.0.dev20170216.zip

Manual builds
=============

Building ITK Python wheels
--------------------------

Build the ITK Python wheel with the following command::

	mkvirtualenv build-itk
	pip install -r requirements-dev.txt
	python setup.py bdist_wheel

Efficiently building wheels for different version of python
-----------------------------------------------------------

If on a given platform you would like to build wheels for different version of python, you can download and build the ITK components independent from python first and reuse them when building each wheel.

Here are the steps:

- Build ITKPythonPackage with ITKPythonPackage_BUILD_PYTHON set to OFF

- Build "flavor" of package using::

	python setup.py bdist_wheel -- \
	  -DITK_SOURCE_DIR:PATH=/path/to/ITKPythonPackage-core-build/ITKs
