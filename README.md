# ITK Python Package

This project configures pyproject.toml files and manages environmental
variables needed to build ITK Python binary wheels on macOS, Linux, and Windows platforms.
Scripts are available for both [ITK infrastructure](https://github.com/insightSoftwareConsortium/ITK) and
ITK external module Python packages.

The Insight Toolkit (ITK) is an open-source, cross-platform system that provides developers
with an extensive suite of software tools for image analysis.
More information is available on the [ITK website](https://itk.org/)
or at the [ITK GitHub homepage](https://github.com/insightSoftwareConsortium/ITK).

## Table of Contents

- [Building Remote Modules with ITKPythonPackage](#building-remote-modules-with-itkpythonpackage)
- [Building ITK Python Wheels](#building-itk-python-wheels)
- [Frequently Asked Questions](#frequently-asked-questions)
- [Additional Information](#additional-information)

## Building Remote Modules with ITKPythonPackage

ITK reusable workflows are available to build and package Python wheels as
part of Continuous Integration (CI) via GitHub Actions runners.
Those workflows can handle the overhead of fetching, configuring, and
running ITKPythonPackage build scripts for most ITK external modules.
See [ITKRemoteModuleBuildTestPackageAction](https://github.com/InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction)
for more information.

> [!NOTE]
> When using`ITKRemoteModuleBuildTestPackageAction` in your remote module, you can specify the `itk-python-package-org` and `itk-python-package-tag` to build with.

For special cases where ITK reusable workflows are not a good fit,
ITKPythonPackage scripts can be directly used to build Python wheels
to target Windows, Linux, and macOS platforms. See
below or the [ITKPythonPackage ReadTheDocs](https://itkpythonpackage.readthedocs.io/en/latest/Build_ITK_Module_Python_packages.html)
documentation for more information on building wheels by hand.

## Building ITK Python Wheels

### Do You Actually Need to Build ITK?

Most users do not need to build ITK from source.

Pre-built ITK binaries are available as downloadable tarballs and the provided download-and-build shell scripts will fetch them automatically.

You may only need to build ITK yourself if you:
- Have a local ITK with custom patches or bug fixes not yet in a release
- Need to build against a specific unreleased commit
- Are developing ITK core itself

If none of the above apply to you, you may download an existing build of ITK from ITK's repository for [ITK Python Builds](https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases). **Or**, use the download-and-build script seen in the [Building Remote Module Wheels](#building-remote-module-wheels) section below.

For more control over your builds, skip to [The Build Process](#the-build-process)

---

### Prerequisites

- Python 3.10 or later
- Git
- Docker (for manylinux builds)
- [Pixi](https://pixi.sh) package manager

**Install Pixi:**
```bash
# Linux or Mac
curl -fsSL https://pixi.sh/install.sh | bash

# Windows
powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"
```

**Clone the repo:**
```bash
git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git
cd ITKPythonPackage
```

---

### Building Remote Module Wheels

#### The Build Process

The build process calls `build_wheels.py`, which runs up to 7 steps:

1. Build SuperBuild support components
2. Build ITK C++ with Python wrapping
3. Build wheels for ITK C++
4. Fix up wheels if needed
5. Import test
6. *(optional)* Build a remote module against the ITK build
7. *(optional)* Build an ITK tarball cache

> [!NOTE]
> When using the download-and-build scripts, steps 2–3 are skipped because the pre-built cache covers them.

You can invoke the `build_wheels.py` script directly for more control shown below

Available pixi platform build environments:

| Platform | Architectures | Python Versions |
|----------|---------------|-----------------|
| `linux` | x86_64, aarch64 | py310, py311 |
| `manylinux228` | x86_64, aarch64 | py310, py311 |
| `macosx` | x86_64, arm64 | py310, py311 |
| `windows` | x86_64 | py310, py311 |


```bash
# Building ITK Python Wheels on macOS for ITK v6.0b01
pixi run python3 scripts/build_wheels.py \
  --platform-env macosx-py310 \
  --itk-git-tag v6.0b01 \
  --no-build-itk-tarball-cache
```

Key options:

| Option                           | Description                                  | Example                       |
|----------------------------------|----------------------------------------------|-------------------------------|
| `--platform-env`                 | Target platform and Python version           | `macosx-py310`                |
| `--build-dir-root`               | Location for build artifacts                 | `/tmp/ITKPythonPackage-build` |
| `--itk-git-tag`                  | ITK version/branch/commit to use             | `0ffcaed`, `main`, `v6.0b01`  |
| `--itk-package-version`          | PEP440 version string for wheels             | `v6.0b01`                     |
| `--manylinux-version`            | Manylinux standard version                   | `_2_28`                       |
| `--module-source-dir`            | Path to remote module to build               | `/path/to/module`             |
| `--itk-module-deps`              | Remote module dependencies                   | `Mod1@tag:Mod2@tag`           |
| `--module-dependencies-root-dir` | Root directory for module dependencies       | `./dependencies`              |
| `--itk-source-dir`               | Path to ITK source (use local development)   | `/path/to/ITK`                |
| `--cleanup`                      | Leave temporary build files after completion | (flag)                        |
| `--no-build-itk-tarball-cache`   | Skip tarball generation (default)            | (flag)                        |
| `--no-skip-itk-build`            | Don't skip ITK build step (default           | (flag)                        |
| `--no-skip-itk-wheel-build`      | Don't skip the ITK wheel build step (default) | (flag)                        |


Run `pixi run python3 scripts/build_wheels.py --help` for the full option list.

> [!NOTE]
> Building ITK from source can take 1-2 hours on typical hardware. Once complete, use `--build-itk-tarball-cache` to save the result and avoid rebuilding.

To use the scripts that take care of the build for you, see this section:

<details>
<summary><strong>Download-and-Build Remote Module Builds</strong></summary>

This is the same process as used in the GitHub Actions CI/CD

```bash
cd ITKRemoteModule
```

#### Linux (manylinux)

Use `dockcross-manylinux-download-cache-and-build-module-wheels.sh`. This script:
1. Downloads the pre-built ITK binary tarball for your platform
2. Extracts it to a local build directory
3. Calls `dockcross-manylinux-build-module-wheels.sh` to build the module wheels inside a manylinux Docker container

Run from your ITK external module root:
```bash
bash dockcross-manylinux-download-cache-and-build-module-wheels.sh cp310
```

> [!NOTE]
> Omit the Python version argument (e.g. `cp310`) to build for all default versions (cp310 and cp311).

#### macOS

Use `macpython-download-cache-and-build-module-wheels.sh`. This script:
1. Installs required tools (aria2, zstd, gnu-tar) via Pixi if not present
2. Downloads and extracts the macOS ITK binary tarball
3. Builds your module wheels for each requested Python version

Run from your module root:
```bash
bash macpython-download-cache-and-build-module-wheels.sh 3.10
```

#### Windows

Use `windows-download-cache-and-build-module-wheels.ps1`. This script:
1. Installs required tools (git, aria2) via Pixi if not present
2. Downloads and extracts the Windows ITK binary zip file
3. Builds your module wheels for each requested Python version

Run from your module root:
```powershell
.\windows-download-cache-and-build-module-wheels.ps1 3.11
```


#### Output

Finished wheels are placed in `<your-module>/dist/`.

</details>


To see how to build wheels for your version of ITK see this section:

<details>
<summary><strong>Building ITK from Source</strong></summary>

If you have a local ITK with custom patches, a bug fix not yet released, or you're developing ITK core itself. Build as follows

Pass `--itk-source-dir` pointing to your local ITK clone. `build_wheels.py` will build ITK from that source instead of re-cloning.

#### manylinux — building ITK from source

Use `dockcross-manylinux-build-wheels.sh` directly (skips the download step):

```bash
ITK_SOURCE_DIR=/path/to/your/ITK \
bash scripts/dockcross-manylinux-build-wheels.sh cp310
```

Key environment variables:

| Variable | Default                                 | Description |
|----------|-----------------------------------------|-------------|
| `ITK_GIT_TAG` | `main`                                  | ITK branch/tag/commit to build |
| `ITK_SOURCE_DIR` | `<build-root>/ITKPythonPackage-build/ITK` | Path to local ITK source (skips git clone) |
| `MANYLINUX_VERSION` | `_2_28`                                 | Manylinux standard to target |
| `IMAGE_TAG` | `20250913-6ea98ba`                      | Dockcross image tag |

#### Linux/macOS/Windows — building ITK from source

Use `build_wheels.py` directly with `--itk-source-dir`:

```bash
# Building on macOS with a specific git tag
pixi run python3 scripts/build_wheels.py \
  --platform-env macosx-py310 \
  --itk-source-dir /path/to/your/ITK \
  --itk-git-tag my-bugfix-branch \
  --no-build-itk-tarball-cache \
  --build-dir-root /tmp/itk-build
```

Add `--build-itk-tarball-cache` if you want to save the result as a reusable tarball.

</details>

To see how to build ITK Python Build Caches, see this section:

<details>
<summary><strong>Building ITK Python Caches</strong></summary>

#### GitHub Compatible Caches

To build the caches compatible with GitHub Actions CI and the ITKPythonBuilds repository. You can run:

On Linux and macOS systems
```bash
bash scripts/make_tarballs.sh  # py310 (optionally add specific version of Python)
```

On Windows systems
```powershell
.\scripts\make_windows_zip.ps1 # py310 (optionally add specific version of Python)
```

> [!IMPORTANT]
> Build caches embed absolute paths. If you extract a tarball to a different path than it was built with, CMake will fail. Standard build paths for CI/CD are:
> - manylinux (Docker): `/work/ITKPythonPackage-build`
> - macOS: `/Users/svc-dashboard/D/P/ITKPythonPackage-build`
> - Windows: `C:\BDR`
>
> This script ensures you are building with the correct conventions

#### Local Caches

To build caches for local use, you can run the `build_wheels.py` script with the `--build-itk-tarball-cache`

#### Publish Tarball Caches

To publish the tarball caches to a GitHub Release, you can run:

> [!NOTE]
> This requires the `GH_TOKEN` environment variable to be set or `gh auth login` to have been run beforehand.
> Tarballs are expected in the parent directory of `--build-dir-root` (POSIX `.tar.zst`) or inside it (Windows `.zip`).

```bash
pixi run -e publish publish-tarball-cache --itk-package-version v6.0b02 --build-dir-root /path/to/build/root
```

Users can also specify the GitHub repository to publish to using `--repo` (defaults to ITKPythonBuilds) and
`--create-release` to create the release if it does not already exist.

</details>

To see how to publish wheels see this section:

<details>
<summary><strong>Publishing Wheels</strong></summary>
This repository contains a script for publishing wheels to PyPI and TestPyPI.

The script can be run with the pixi environment as such:

> [!NOTE]
> This script assumes you have the `TWINE_USERNAME` and `TWINE_PASSWORD` environment variables set or the
> `.pypirc` file configured on your machine. An example `.pypirc` can be seen in the root of this repository

```bash
pixi run -e publish publish-wheels --dist-directory /path/to/dist/
```

You can also optionally pass in `--test` to publish to TestPyPI for validation before uploading to production,
`--repository-url` to specify a custom package index, or `--skip-existing` to skip already-uploaded wheels.

</details>

---
## Frequently Asked Questions

### What target platforms and architectures are supported?

ITKPythonPackage currently supports building wheels for the following platforms and architectures:

- Windows 10/11 x86_64 platforms
- macOS arm64 (Apple Silicon)
- macOS x86_64 (Intel)
- Linux glibc 2.17+ (e.g. Ubuntu 20.04+) x86_64
- Linux glibc 2.28+ (e.g. Ubuntu 20.04+) aarch64 (ARMv8)

Python 3.10+ is required.

[ITKRemoteModuleBuildTestPackageAction](https://github.com/InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction)
CI workflows support Python 3.10–3.11 on GitHub-hosted runners for:
- Ubuntu x86_64
- Ubuntu aarch64 (ARM)
- macOS arm64 (Apple Silicon)
- Windows x86_64

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
