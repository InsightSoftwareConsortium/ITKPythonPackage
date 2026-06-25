# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ITKPythonPackage is a cross-platform build system for creating Python binary wheels for the Insight Toolkit (ITK) — an open-source C++ image analysis library. It builds wheels for ITK itself and for ITK external (remote) modules across Linux, macOS, and Windows (x86_64 and arm64/aarch64).

ITK external modules require pre-built ITK artifacts. These are cached as [ITKPythonBuilds](https://github.com/InsightSoftwareConsortium/ITKPythonBuilds) releases to avoid rebuilding ITK for every module.

## Build System

### Running a build

The primary entry point is `scripts/build_wheels.py`, orchestrated via pixi:

```sh
pixi run build-itk-wheels
```

Or directly:
```sh
python scripts/build_wheels.py
```

### Environment management

**pixi** (conda-like) manages reproducible build environments defined in `pixi.toml`. Environments are composed per-platform and per-Python-version (e.g., `manylinux228-py310`, `macosx-py311`).

### Key environment variables (GitHub Actions compatible)

- `ITK_PACKAGE_VERSION` — Version string for wheels
- `ITKPYTHONPACKAGE_TAG` — ITKPythonPackage version/tag to use
- `ITKPYTHONPACKAGE_ORG` — GitHub org (default: InsightSoftwareConsortium)
- `ITK_MODULE_PREQ` — Module dependencies (`org/repo@tag:org/repo@tag:...`)
- `CMAKE_OPTIONS` — Extra CMake flags
- `MANYLINUX_VERSION` — Manylinux ABI version (_2_28, _2_34, etc.)
- `MACOSX_DEPLOYMENT_TARGET` — macOS minimum deployment target

### Linting

```sh
pre-commit run --all-files
```

Shell script linting was previously via `.travis.yml`; now uses pre-commit hooks.

## Architecture

### Python build scripts (`scripts/`)

Class hierarchy for platform-specific wheel building:

- **`build_wheels.py`** — Main driver. Detects platform/arch, selects pixi environment, creates platform-specific build instance.
- **`build_python_instance_base.py`** — Abstract base class defining the shared build pipeline (download, configure, build, package).
- **`linux_build_python_instance.py`** — Linux: TBB support, `auditwheel` for manylinux compliance.
- **`macos_build_python_instance.py`** — macOS: `delocate` for dylib relocation.
- **`windows_build_python_instance.py`** — Windows: `delvewheel` for DLL bundling.

Supporting scripts:
- **`pyproject_configure.py`** — Generates `pyproject.toml` from `pyproject.toml.in` template with platform-specific substitutions.
- **`wheel_builder_utils.py`** — Shared utilities (subprocess wrappers, path handling, env parsing).
- **`cmake_argument_builder.py`** — Builds CMake args for both direct invocation (`-DKEY=VALUE`) and scikit-build-core (`--config-setting=cmake.define.KEY=VALUE`).
- **`BuildManager.py`** — JSON-based build step tracking for resuming interrupted builds.

### CMake layer (`cmake/`)

- **`ITKPythonPackage_Utils.cmake`** — Utility functions for module dependency resolution, wheel-to-group mapping.
- **`ITKPythonPackage_BuildWheels.cmake`** — Wheel-specific CMake build configuration.
- **`ITKPythonPackage_SuperBuild.cmake`** — ITK + dependencies superbuild.

### Wheel targets

Defined in `BuildWheelsSupport/WHEEL_NAMES.txt`: itk-core, itk-numerics, itk-io, itk-filtering, itk-registration, itk-segmentation, itk-meta.

### Build backend

Uses **scikit-build-core**. The `pyproject.toml.in` template is the single source of truth for project metadata.

## Shell script entry points

Legacy shell/PowerShell scripts are preserved for backward compatibility with existing CI workflows:
- `scripts/dockcross-manylinux-download-cache-and-build-module-wheels.sh` (Linux)
- `scripts/macpython-download-cache-and-build-module-wheels.sh` (macOS)
- `scripts/windows-download-cache-and-build-module-wheels.ps1` (Windows)

These scripts delegate to the Python build system internally.

### Commit message convention

This project follows the ITK commit message convention: `PREFIX: Description`. Valid prefixes: `BUG:`, `COMP:`, `DOC:`, `ENH:`, `PERF:`, `STYLE:`. Enforced via commitizen (configured in `pyproject.toml`, validated by the `commit-msg` pre-commit hook).

## Related repositories

- [ITK](https://github.com/InsightSoftwareConsortium/ITK) — The C++ toolkit itself
- [ITKPythonBuilds](https://github.com/InsightSoftwareConsortium/ITKPythonBuilds) — Cached ITK build artifacts
- [ITKRemoteModuleBuildTestPackageAction](https://github.com/InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction) — GitHub Actions reusable workflows for building/testing/packaging
