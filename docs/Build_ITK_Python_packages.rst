==============================
Build ITK Python Packages
==============================

This section describes how to build ITK's core Python wheels
(``itk-core``, ``itk-numerics``, ``itk-io``, ``itk-filtering``,
``itk-registration``, ``itk-segmentation``, and ``itk-meta``). In most cases, the pre-built ITK binary wheels can be used.

You may only need to build ITK from source if you need a custom patch, a specific unreleased
commit, or are developing ITK core itself.

.. include:: Prerequisites.rst

Automated platform scripts
==========================

Steps required to build wheels on Linux, macOS and Windows have been
automated. The following sections outline how to use the associated scripts.


Overview
========

The build is driven by ``scripts/build_wheels.py``, which orchestrates up to
seven sequential steps:

1. Build SuperBuild support components (oneTBB and other ITK dependencies)
2. Build ITK C++ with Python wrapping
3. Build Python wheels for each ITK subpackage
4. Fix up wheels if platform requires (``auditwheel`` / ``delocate`` / ``delvewheel``)
5. Import test
6. *(optional)* Build a remote module against the ITK build
7. *(optional)* Create a reusable ITK build tarball cache

Step state is persisted to ``<build-dir-root>/dist/build_report-<platform>.json`` so that a
build interrupted part-way through can be resumed by re-running the same command.


Setup
=====

Clone the repository::

   git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git
   cd ITKPythonPackage


Platform Environments
=====================

Each Pixi environment targets a specific OS and Python version. Pass the
environment name to ``--platform-env``:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - ``--platform-env``
     - Notes
   * - ``linux-py310``
     - Native Linux (GCC, glibc of host)
   * - ``linux-py311``
     - Native Linux (GCC, glibc of host)
   * - ``manylinux228-py310``
     - Portable Linux ≥ glibc 2.28 (x86_64 or aarch64 via Docker)
   * - ``manylinux228-py311``
     - Portable Linux ≥ glibc 2.28 (x86_64 or aarch64 via Docker)
   * - ``macosx-py310``
     - macOS (x86_64 and arm64)
   * - ``macosx-py311``
     - macOS (x86_64 and arm64)
   * - ``windows-py310``
     - Windows x86_64 (MSVC 2022)
   * - ``windows-py311``
     - Windows x86_64 (MSVC 2022)

If ``--platform-env`` is omitted, the platform is auto-detected from the
host OS and defaults to Python 3.10.


Building Wheels
===============

manylinux
---------

On any linux distribution with docker and bash installed, running the script dockcross-manylinux-build-wheels.sh will create 64-bit wheels for python 3.10+ in the dist directory.

.. code-block:: bash

   ./scripts/dockcross-manylinux-build-wheels.sh  # py310 optionally specify python version

Or you can build using a specific platform environment using:

Linux
-----

.. code-block:: bash

   pixi run python3 scripts/build_wheels.py \
     --platform-env linux-py310 \
     --itk-git-tag v6.0b01 \
     --no-build-itk-tarball-cache

macOS
-----

.. code-block:: bash

   pixi run python3 scripts/build_wheels.py \
     --platform-env macosx-py310 \
     --itk-git-tag v6.0b01 \
     --no-build-itk-tarball-cache

Windows
-------

Similarly, on windows

.. code-block:: powershell

   pixi run python3 scripts/build_wheels.py `
     --platform-env windows-py310 `
     --itk-git-tag v6.0b01 `
     --no-build-itk-tarball-cache


Finished wheels are placed in ``<build-dir-root>/dist/``.

.. note::
   Building ITK from source takes 1–2 hours on typical hardware. Pass
   ``--build-itk-tarball-cache`` to save the result as a reusable tarball
   and avoid rebuilding on subsequent runs.


Key Options
===========

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Option
     - Default
     - Description
   * - ``--platform-env``
     - auto-detected
     - Target platform and Python version (see table above)
   * - ``--itk-git-tag``
     - ``main``
     - ITK version, branch, or commit to build
   * - ``--itk-package-version``
     - auto (git describe)
     - PEP 440 version string embedded in the wheels
   * - ``--build-dir-root``
     - ``../ITKPythonPackage-build``
     - Root directory for all build artifacts
   * - ``--manylinux-version``
     - ``_2_28``
     - Manylinux compatibility standard (e.g. ``_2_28``, ``_2_34``)
   * - ``--itk-source-dir``
     - cloned automatically
     - Path to a local ITK checkout (skips git clone)
   * - ``--module-source-dir``
     - *(none)*
     - Path to an ITK external module to build against the ITK build
   * - ``--itk-module-deps``
     - *(none)*
     - Colon-delimited prerequisite modules (``org/repo@tag:org/repo@tag``)
   * - ``--build-itk-tarball-cache``
     - off
     - Package the ITK build as a reusable ``.tar.zst`` / ``.zip``
   * - ``--no-build-itk-tarball-cache``
     - *(default)*
     - Skip tarball generation
   * - ``--skip-itk-build`` / ``--no-skip-itk-build``
     - off
     - Skip step 2 (ITK C++ build) when a build already exists
   * - ``--skip-itk-wheel-build`` / ``--no-skip-itk-wheel-build``
     - off
     - Skip step 3 (wheel build) when wheels already exist
   * - ``--cleanup``
     - off
     - Remove intermediate build files after completion
   * - ``--use-ccache``
     - off
     - Enable ccache to speed up recompilation
   * - ``--macosx-deployment-target``
     - ``10.7``
     - Minimum macOS version for compiled binaries
   * - ``--use-sudo`` / ``--no-use-sudo``
     - off
     - Pass ``sudo`` to Docker commands (manylinux only)

Any remaining positional arguments are forwarded to CMake as ``-D`` definitions,
for example::

   pixi run python3 scripts/build_wheels.py \
     --platform-env macosx-py310 \
     --itk-git-tag v6.0b01 \
     -DBUILD_SHARED_LIBS:BOOL=OFF


Environment Variable Equivalents
---------------------------------

All ``--`` options can alternatively be set as environment variables, which is
useful in CI pipelines:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Environment Variable
     - Equivalent Option
   * - ``ITK_GIT_TAG``
     - ``--itk-git-tag``
   * - ``ITK_PACKAGE_VERSION``
     - ``--itk-package-version``
   * - ``ITK_SOURCE_DIR``
     - ``--itk-source-dir``
   * - ``MANYLINUX_VERSION``
     - ``--manylinux-version``
   * - ``TARGET_ARCH``
     - target architecture (``x64`` or ``aarch64``)
   * - ``IMAGE_TAG``
     - Docker image tag for manylinux builds
   * - ``NO_SUDO``
     - ``--no-use-sudo``
   * - ``USE_CCACHE``
     - ``--use-ccache``
   * - ``CMAKE_OPTIONS``
     - extra CMake ``-D`` definitions
   * - ``MACOSX_DEPLOYMENT_TARGET``
     - ``--macosx-deployment-target``


Building from a Local ITK Source
=================================

If you have a local ITK checkout with custom patches or an unreleased fix, pass
``--itk-source-dir`` to use it instead of cloning from GitHub:

.. code-block:: bash

   pixi run python3 scripts/build_wheels.py \
     --platform-env macosx-py310 \
     --itk-source-dir /path/to/your/ITK \
     --itk-git-tag my-bugfix-branch \
     --no-build-itk-tarball-cache

For manylinux, use the shell wrapper which handles Docker volume mounting:

.. code-block:: bash

   ITK_SOURCE_DIR=/path/to/your/ITK \
   bash scripts/dockcross-manylinux-build-wheels.sh cp310


Building ITK Tarball Caches
============================

Tarball caches package the entire ITK build output (headers, libraries, wrapper
artifacts) so that external module builds can skip the costly ITK compilation step.
These are the same caches distributed via `ITKPythonBuilds
<https://github.com/InsightSoftwareConsortium/ITKPythonBuilds>`_ releases.

By default these scripts build for python version 3.10 and 3.11 but you can optionally add a specific version to build for

Linux / macOS:

.. code-block:: bash

   ITK_GIT_TAG=v6.0b01
   bash scripts/make_tarballs.sh py310

Windows (PowerShell):

.. code-block:: powershell

   $env:ITK_GIT_TAG = "v6.0b01"
   .\scripts\make_windows_zip.ps1 py310

Or via ``build_wheels.py`` directly:

.. code-block:: bash

   pixi run python3 scripts/build_wheels.py \
     --platform-env macosx-py310 \
     --itk-git-tag v6.0b01 \
     --build-itk-tarball-cache

.. important::
   Build caches embed absolute paths. They must be extracted to the same path
   they were built from or CMake will fail to locate required files. The
   standard CI/CD paths are:

   - **manylinux (Docker)**: ``/work/ITKPythonPackage-build``
   - **macOS**: ``/Users/svc-dashboard/D/P/ITKPythonPackage-build``
   - **Windows**: ``C:\BDR``

   The ``make_tarballs.sh`` and ``make_windows_zip.ps1`` scripts enforce these
   paths automatically.


Output Artifacts
================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Artifact
     - Location
   * - Built wheels
     - ``<build-dir-root>/dist/*.whl``
   * - Effective command line
     - ``<build-dir-root>/effective_cmdline_<env>.sh``
   * - manylinux tarball caches
     - ``<build-dir-root>/ITKPythonBuilds-manylinux_2_28-*.tar.zst``
   * - Linux tarball caches
     - ``<build-dir-root>/ITKPythonBuilds-linux-*.tar.zst``
   * - macOS tarball caches
     - ``<build-dir-root>/ITKPythonBuilds-macosx-*.tar.zst``
   * - Windows ZIP cache
     - ``<build-dir-root>/ITKPythonBuilds-windows.zip``

Example wheel names::

   itk-6.0.0-cp310-cp310-manylinux_2_28_x86_64.whl
   itk-6.0.0-cp310-cp310-macosx_13_0_arm64.whl
   itk-6.0.0-cp310-cp310-win_amd64.whl


Testing Built Wheels
====================

Install and smoke-test a wheel directly from the ``dist/`` directory:

.. code-block:: bash

   pip install dist/itk-6.0.0-cp310-cp310-macosx_13_0_arm64.whl
   python -c "import itk; print(itk.__version__)"


Troubleshooting
===============

Path Length Issues (Windows)
-----------------------------

If you encounter path length errors:

Windows has a 260-character path limit by default. Use a short build directory
(e.g. ``C:\BDR``) and optionally enable long path support:

.. code-block:: powershell

   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
     -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force

Antivirus Conflicts (Windows)
------------------------------

The build creates and deletes large numbers of files rapidly, which can trigger
Windows Defender and produce "Access Denied" errors. Add the build directory to
Windows Defender exclusions:

1. Open **Windows Security → Virus & threat protection → Manage settings**
2. Scroll to **Exclusions → Add or remove exclusions**
3. Add the build root (e.g. ``C:\BDR``)

Docker Permissions (Linux)
---------------------------

If Docker requires ``sudo``, pass ``--use-sudo`` to ``build_wheels.py`` or set
``NO_SUDO=`` (empty string) before running the manylinux shell script. To add
your user to the ``docker`` group instead::

   sudo usermod -aG docker $USER
   # Then log out and back in
