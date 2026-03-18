Prerequisites
=============

The following tools are required to build ITK Python wheels locally.

All Platforms
-------------

`Pixi <https://pixi.sh>`_ is the primary build environment manager. It automatically
provisions the correct Python version, compiler toolchain, CMake, Ninja, and all
other build dependencies for each target platform. Manual installation of compilers
or CMake is not required when using Pixi.

Install Pixi:

.. code-block:: bash

   # Linux or macOS
   curl -fsSL https://pixi.sh/install.sh | bash

   # Windows (PowerShell)
   powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"

You will also need `Git <https://git-scm.com>`_ 2.x or later.

Linux
-----

Portable manylinux builds require Docker (or an OCI-compatible runtime such as
Podman or nerdctl) to run the manylinux container environment.

Install Docker by following the official `Docker Engine installation guide
<https://docs.docker.com/engine/install/>`_.

macOS
-----

No additional tools are required beyond Pixi. The Pixi ``macosx-build``
environment provides the Clang 1.10.0 compiler toolchain and the
`delocate <https://github.com/matthew-brett/delocate>`_ wheel repair utility.

Windows
-------

`Microsoft Visual Studio 2022 <https://visualstudio.microsoft.com/vs/>`_
(or the Build Tools for Visual Studio 2022) with the
**Desktop development with C++** workload is required.

.. note::
   Pixi environments provision Python, CMake, Ninja, and build helpers
   (``auditwheel`` on Linux, ``delocate`` on macOS, ``delvewheel`` on Windows)
   automatically. Only Docker (Linux) and MSVC (Windows) require separate installation.
