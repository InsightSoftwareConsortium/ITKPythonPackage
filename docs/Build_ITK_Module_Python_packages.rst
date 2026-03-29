=====================================
Build ITK Module Python Packages
=====================================

ITK is organized into *modules*. Community members can extend ITK by developing
an ITK *external module* in a separate repository. When a module meets community
standards for documentation and maintenance it may be included in the ITK build
as a *remote module*.

This section describes how to create, build, and publish Python packages for
ITK remote and external modules to PyPI.


Create a Module
===============

To scaffold a new ITK module with Python wrapping, use the official template::

  python -m pip install cookiecutter
  python -m cookiecutter gh:InsightSoftwareConsortium/ITKModuleTemplate
  # Fill in the information requested at the prompts

Fill in the prompts, then add your C++ filter classes. See
`Chapter 9 of the ITK Software Guide
<https://itk.org/ITKSoftwareGuide/html/Book1/ITKSoftwareGuide-Book1ch9.html>`_
for guidance on populating the module and writing ``.wrap`` files for SWIG.


GitHub Actions Workflows
==============================

For most ITK external modules, the recommended and easiest path to building, testing, and
publishing Python wheels is the
`ITKRemoteModuleBuildTestPackageAction
<https://github.com/InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction>`_
reusable workflow. It handles fetching, configuring, and running
ITKPythonPackage build scripts automatically.

Every pull request and push triggers a build that:

- Compiles and runs your module's C++ tests
- Generates Linux, macOS, and Windows Python wheels

Wheel artifacts are downloadable from the **Artifacts** section of the
GitHub Actions run page.

.. figure:: images/GitHubActionArtifacts.png
   :alt: GitHub Action Artifacts

To pin the specific ITKPythonPackage version used by the workflow (defaults are shown below):

.. code-block:: yaml

   uses: InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction/.github/workflows/build-test-package.yml@v5.4.5
   with:
     itk-python-package-org: InsightSoftwareConsortium
     itk-python-package-tag: main

.. include:: Prerequisites.rst

Manual Builds
=============

For cases where the reusable workflow is not a good fit, the
download-and-build scripts can be run locally. Each script:

1. Downloads and installs the necessary build packages
2. Downloads the pre-built ITK binary tarball for the target platform from
   `ITKPythonBuilds <https://github.com/InsightSoftwareConsortium/ITKPythonBuilds>`_
3. Extracts it to a local build directory
4. Builds your module wheels against the pre-built ITK

.. important::
    Place and run the script from your module's root directory. Or specify exact paths using the environment variables below

Set the ITK PEP 440 compliant version before running any script::

   export ITK_PACKAGE_VERSION=v6.0b01   # Linux / macOS
   $env:ITK_PACKAGE_VERSION = "v6.0b01" # Windows PowerShell

Linux (manylinux)
-----------------

Requires Docker. Produces ``manylinux_2_28`` portable wheels.

.. code-block:: bash

   cd ~/ITKMyModule
   # First build — downloads ITK cache, then builds module wheels
   export MODULE_SRC_DIRECTORY=/path/to/module
   bash ITKPythonPackage/scripts/dockcross-manylinux-download-cache-and-build-module-wheels.sh cp310

   # Subsequent builds — reuses the downloaded cache
   bash ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh cp310

Omit the Python version argument to build all supported versions (cp310 and cp311):

.. code-block:: bash

   export MODULE_SRC_DIRECTORY=/path/to/module
   bash ITKPythonPackage/scripts/dockcross-manylinux-download-cache-and-build-module-wheels.sh

macOS
-----

.. code-block:: bash

   cd ~/ITKMyModule
   export MODULE_SRC_DIRECTORY=/path/to/module
   bash ITKPythonPackage/scripts/macpython-download-cache-and-build-module-wheels.sh 3.10 3.11

Windows
-------

Open a PowerShell terminal:

.. code-block:: powershell

   cd C:\ITKMyModule
   $env:ITK_PACKAGE_VERSION = "v6.0b01"
   $env:MODULE_SRC_DIRECTORY = /path/to/module
   .\ITKPythonPackage\scripts\windows-download-cache-and-build-module-wheels.ps1 -python_version_minor 10

Build multiple Python versions:

.. code-block:: powershell

   foreach ($v in @(10, 11)) {
       .\ITKPythonPackage\scripts\windows-download-cache-and-build-module-wheels.ps1 -python_version_minor $v
   }

.. important::
   Use a short build path (e.g. ``C:\BDR``) to avoid Windows 260-character
   path length limits. See the Troubleshooting section in
   :doc:`Build_ITK_Python_packages` for details.

Key environment variables:

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Variable
     - Default
     - Description
   * - ``ITK_PACKAGE_VERSION``
     - ``v6.0b01``
     - PEP 440 ITK release to build against
   * - ``TARGET_ARCH``
     - ``x64``
     - ``x64`` or ``aarch64``
   * - ``IMAGE_TAG``
     - ``20250913-6ea98ba``
     - Dockcross Docker image tag
   * - ``MODULE_SRC_DIRECTORY``
     - script directory
     - Path to your module source
   * - ``MODULE_DEPS_DIR``
     - platform dependant
     - Root directory for module dependency checkouts
   * - ``DASHBOARD_BUILD_DIRECTORY``
     - platform dependant
     - Root directory for build artifacts
   * - ``MANYLINUX_VERSION``
     - ``_2_28``
     - Manylinux compatibility standard
   * - ``CMAKE_OPTIONS``
     - *(empty)*
     - Extra CMake ``-D`` definitions
   * - ``ITKPYTHONPACKAGE_TAG``
     - ``main``
     - ITKPythonPackage branch/tag to fetch
   * - ``ITKPYTHONPACKAGE_ORG``
     - ``InsightSoftwareConsortium``
     - ITKPythonPackage organization to fetch
   * - ``NO_SUDO``
     - *(unset)*
     - Set to skip ``sudo`` for Docker commands
   * - ``DYLD_LIBRARY_PATH``
     - *(unset)*
     - Extra library paths to bundle into wheels


Use the Build Script Directly
====================================

For more control over build option, call ``build_wheels.py`` directly with
``--module-source-dir``. This approach will create a local ITK build by default:

.. code-block:: bash

   pixi run python3 scripts/build_wheels.py \
     --platform-env macosx-py310 \
     --itk-git-tag v6.0b01 \
     --module-source-dir /path/to/ITKMyModule \
     --no-skip-itk-build \
     --no-skip-itk-wheel-build \
     --no-build-itk-tarball-cache


Module Dependencies
===================

If your module depends on other ITK external modules, list them with
``--itk-module-deps`` (or the ``ITK_MODULE_PREQ`` environment variable for the
shell scripts):

.. code-block:: bash

   pixi run python3 scripts/build_wheels.py \
     --platform-env macosx-py310 \
     --itk-git-tag v6.0b01 \
     --module-source-dir /path/to/ITKMyModule \
     --itk-module-deps "InsightSoftwareConsortium/ITKMeshToPolyData@v1.0.0" \
     --no-build-itk-tarball-cache

For multiple dependencies, separate them with colons in **dependency order**
(each module listed before the modules that depend on it):

.. code-block:: bash

   --itk-module-deps "org/ITKModA@v1.0:org/ITKModB@v2.1:org/ITKModC@main"

The format for each entry is ``<github-org>/<repo-name>@<git-tag-or-commit>``.

For the download-and-build shell scripts, set ``ITK_MODULE_PREQ`` instead:

.. code-block:: bash

   export ITK_MODULE_PREQ="org/ITKModA@v1.0:org/ITKModB@v2.1"
   bash ITKPythonPackage/scripts/dockcross-manylinux-download-cache-and-build-module-wheels.sh cp310

Dependencies are cloned to ``<module-dependencies-root-dir>/`` before the
main module build begins.


Third-Party Libraries
=====================

If your module links against a third-party library that is not part of ITK,
the wheel repair tools (``auditwheel``, ``delocate``, ``delvewheel``) need
to be able to find it to bundle it into the wheel.

**Linux**: add the library's directory to ``LD_LIBRARY_PATH`` before running
the build script::

   export LD_LIBRARY_PATH=/path/to/mylib/lib:$LD_LIBRARY_PATH

**macOS**: add the directory to ``DYLD_LIBRARY_PATH``::

   export DYLD_LIBRARY_PATH=/path/to/mylib/lib:$DYLD_LIBRARY_PATH

**Windows**: pass the library directory via ``--lib-paths`` (or the
``-setup_options`` parameter of the PowerShell script):

.. code-block:: powershell

   .\windows-download-cache-and-build-module-wheels.ps1 `
     -python_version_minor 10 `
     -setup_options "--exclude-libs nvcuda.dll"


Output
======

Finished wheels are placed in ``dist/`` inside your module directory
(or ``<module-src-directory>/dist/`` when running ``build_wheels.py`` directly).

Example output::

   dist/
   itk-mymodule-1.0.0-cp310-cp310-manylinux_2_28_x86_64.whl
   itk-mymodule-1.0.0-cp310-cp310-macosx_13_0_arm64.whl
   itk-mymodule-1.0.0-cp310-cp310-win_amd64.whl


Uploading to PyPI
=================

Using the Publish Environment
-----------------------------

ITKPythonPackage provides a ``publish`` Pixi environment with ``twine``
pre-configured. Set your PyPI credentials (see ``.pypirc.example`` in the
repository root) and run:

.. code-block:: bash

   export TWINE_USERNAME=__token__
   export TWINE_PASSWORD=pypi-<your-token>

   # Test on TestPyPI first
   pixi run -e publish publish-wheels \
     --dist-directory /path/to/module/dist \
     --test

   # Then upload to production PyPI
   pixi run -e publish publish-wheels \
     --dist-directory /path/to/module/dist

Pass ``--skip-existing`` to skip already-uploaded wheels when re-running after
a partial upload failure.

Manual Upload
-------------

Alternatively, install and use ``twine`` directly.

Test on TestPyPI first::

   pip install twine
   twine upload -r testpypi dist/*.whl

Then upload to production PyPI::

   twine upload dist/*.whl

Your package can then be installed with::

   pip install itk-<your-short-module-name>

Automated Upload via GitHub Actions
-------------------------------------

To automate publishing on every tagged release:

1. Create a PyPI API token at `<https://pypi.org/manage/account/token/>`_.
   Name it ``itk-<your-module-name>-github-action`` and scope it to your
   package (scope becomes available after the first manual upload).

   .. figure:: images/PyPIToken.png
      :alt: PyPI Token

2. In your GitHub repository, go to **Settings → Secrets → Actions** and
   add a secret named ``pypi_password`` with the token value (starts with
   ``pypi-``).

   .. figure:: images/GitHubPyPISecret.png
      :alt: GitHub PyPI token secret

3. Create a GitHub Release (via **Releases → Draft a new release**).
   The tag name should match the version in your ``pyproject.toml``.

   .. figure:: images/GitHubReleaseTag.png
      :alt: GitHub Release Tag

The ``ITKRemoteModuleBuildTestPackageAction`` workflow will detect the tag
and upload wheels automatically.
