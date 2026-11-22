# AGENTS.md

Instructions for agentic coding tools working in ITKPythonPackage. This
file is the authoritative one; `CLAUDE.md` points here.

Read the "Worked example" section first. It answers the most common
request shape end to end, with every command line argument written out.

## The one rule that breaks every build

**Always pass `-e <platform-env>` to `pixi run`.** A bare `pixi run` uses
the `default` environment, which does not carry the pinned `cmake`,
`ninja`, `doxygen`, or `git`. The build aborts immediately and tells you
the environment to use, so this is loud rather than silent, but it is
still the single most common mistake.

```bash
pixi run -e macosx-py311 python scripts/build_wheels.py ...   # correct
pixi run python scripts/build_wheels.py ...                   # aborts
```

The environment name must match the platform:

| Platform                      | `--platform-env`     |
| ----------------------------- | -------------------- |
| macOS arm64                   | `macosx-py311`       |
| Linux x86_64 / aarch64 native | `linux-py311`        |
| Linux via manylinux container | `manylinux228-py311` |
| Windows x86_64                | `windows-py311`      |

`manylinux228-py311` is only valid inside the manylinux container. Start
the container with `scripts/dockcross-manylinux-build-wheels.sh`, which
runs `build_wheels.py` there; on the host `build_wheels.py` refuses that
environment rather than produce `linux_x86_64` wheels.

### Deliberately using host-system tools

To build with the tools already on your `PATH` instead of pixi's, set
the environment name to `hostsystem`. This opts out of both the
environment guard and pixi tool resolution:

```bash
PIXI_ENVIRONMENT_NAME=hostsystem python scripts/build_wheels.py \
    --platform-env macosx-py311 ...
```

Use this when you intend to build against a system compiler or a
locally built tool. It is an escape hatch, not the normal path: nothing
is pinned, so reproducibility is yours to manage.

## Release wheels: building every PyPI wheel

A release publishes 8 wheels for each of 4 targets, 32 in all. No single
machine builds every target, so a full set takes three hosts, each with
pixi and Git 2.x (see docs/Prerequisites.rst):

| Target              | Build host                            |
| ------------------- | ------------------------------------- |
| `macos-arm64`       | Apple Silicon Mac                     |
| `manylinux-aarch64` | the same Mac, or a Linux aarch64 host |
| `manylinux-x64`     | Linux x86_64                          |
| `windows-x64`       | Windows x64                           |

The manylinux targets also need Docker, and Windows needs the Visual Studio
2022 C++ build tools.

On each host, from a clone of this repository:

```bash
pixi run release-wheels <itk-ref> <package-version> --dry-run   # the plan
pixi run release-wheels <itk-ref> <package-version>
pixi run release-wheels <itk-ref> <package-version> --targets manylinux-aarch64
```

`release-wheels` picks the targets the host can build (`--targets` narrows
them), fetches the ITK ref, and sets `SOURCE_DATE_EPOCH` from the ITK commit
so a rebuild of the same commit is byte-comparable. Each build uses the
compiler cache, runs the import test, and fails if a wheel is over PyPI's
100 MB limit. The wheels land in:

| Target    | Wheels                                                  |
| --------- | ------------------------------------------------------- |
| macOS     | `../ITKPythonPackage-build/dist/`                       |
| Windows   | `C:\BDR\dist\`                                          |
| manylinux | `../ITKPythonPackage-manylinux_2_28-<arch>-build/dist/` |

### Keeping rebuilds fast

- **Keep the compiler cache between releases.** A warm cache serves
  nearly every compile. The defaults are ccache's own directory natively,
  sccache's on Windows, and `~/.cache/itk-ccache-manylinux<version>-<arch>`
  for the containers; set `CCACHE_DIR`, `SCCACHE_DIR`, or
  `ITK_CONTAINER_CCACHE_DIR` to move them.
- **A cache serves any clone and build root.** The build sets
  `CCACHE_BASEDIR` (the common parent of the checkout, the build root, and
  the ITK source) or `SCCACHE_BASEDIRS` (each of them), so paths are hashed
  relative to them. Building ITKCommon from a second directory hit 99.9%
  with them and 0% (ccache) or 55% (sccache) without. Set either variable
  yourself to override it. `__FILE__` in the wheels is a relative path:
  ccache passes relative paths to the compiler, and on Windows the build
  adds `-d1trimfile:` for each of those directories to `CMAKE_C_FLAGS` and
  `CMAKE_CXX_FLAGS`.
- **A busy shared host slows the build even with idle cores.** ninja's
  load limit (`ITK_BUILD_LOAD_LIMIT`, default the hardware thread count)
  holds back new jobs while the load average is above it. Set it higher on a
  host whose load comes from other users.

Before uploading, copy every host's `dist/*.whl` into one place and check
the set: 8 wheels per target, each named `*-cp311-abi3-<platform>.whl`, one
version throughout.

### Uploading to TestPyPI first

Upload the full set to TestPyPI and install it from there before anything
goes to PyPI. A file can be uploaded only once, on TestPyPI as on PyPI, so
use a fresh development version (for example `6.0b3.dev1`) for each trial.

1. **Get access.** TestPyPI accounts are separate from PyPI and GitHub.
   Enable two-factor authentication, then ask an owner of the `itk` and
   `itk-*` projects at https://test.pypi.org/project/itk/ to add you as a
   maintainer; accept the invitations. A missing invitation shows as
   `403 Forbidden` on that project's first wheel.
2. **Make a token** with scope "Entire account" at
   https://test.pypi.org/manage/account/token/ (a token for one project
   cannot upload the others or create a new one).
3. **Put it in `~/.pypirc`**, readable only by you, with `testpypi` listed
   in `index-servers` (twine ignores sections the list does not name):

   ```ini
   [distutils]
   index-servers =
     pypi
     testpypi

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-...
   ```

4. **Upload** each target's wheels; `--skip-existing` makes a retry safe:

   ```bash
   pixi run -e publish publish-wheels --dist-directory <dist> \
       --repository testpypi --skip-existing
   ```

5. **Install and test on each platform** in a clean environment. New
   files can take several minutes to reach every TestPyPI mirror; until
   then pip reports "No matching distribution" for some of them. Take the
   `itk*` packages from TestPyPI without dependencies and everything else
   from PyPI, because TestPyPI holds unrelated test uploads of packages
   such as numpy:

   ```bash
   python -m venv /tmp/itk-testpypi && . /tmp/itk-testpypi/bin/activate
   python -m pip install --no-deps --index-url https://test.pypi.org/simple/ \
       itk==<version> itk-core==<version> itk-numerics==<version> \
       itk-io==<version> itk-filtering==<version> \
       itk-filtering-extra==<version> itk-registration==<version> \
       itk-segmentation==<version>
   python -m pip install numpy
   python -m pip check
   python -c "import itk; print(itk.Version.GetITKVersion())"
   ```

   Run it with the oldest and newest supported Python (3.11 and the
   latest), on each of macOS arm64, Linux x86_64, Linux aarch64, and
   Windows x64.

## Worked example

> "Build Python packages on my Mac only, with
> `-mtune=native -march=native` and macOS 26, for PR 6875 which is not
> merged yet, so I can test it in my environment."

Four things are being asked for: a local macOS build, custom compiler
flags, a non-default deployment target, and ITK source from an unmerged
pull request. Do them in this order.

**Step 1: get the PR source.** The build script runs `git fetch --tags
origin` and then `git checkout <tag>`. It does **not** fetch
`pull/N/head` refs, so a pull request ref must be fetched by hand first.

```bash
ITK_SRC="$HOME/src/ITK"
git -C "$ITK_SRC" fetch origin pull/6875/head:pr-6875
git -C "$ITK_SRC" checkout pr-6875
git -C "$ITK_SRC" rev-parse --short HEAD     # record this
```

**Step 2: build.** Positional arguments after the flags are passed
through to CMake verbatim.

```bash
pixi run -e macosx-py311 python scripts/build_wheels.py \
    --platform-env macosx-py311 \
    --itk-source-dir "$ITK_SRC" \
    --itk-git-tag pr-6875 \
    --macosx-deployment-target 26.0 \
    --build-dir-root "$HOME/src/ITKPythonPackage-build" \
    --no-build-itk-tarball-cache \
    --use-ccache \
    -DCMAKE_C_FLAGS:STRING="-mtune=native -march=native" \
    -DCMAKE_CXX_FLAGS:STRING="-mtune=native -march=native"
```

**Step 3: verify you built what was asked for.** A failed checkout in
step 1 prints a warning and keeps whatever commit was already there, so
confirm the source and the resulting tag rather than assuming:

```bash
git -C "$ITK_SRC" rev-parse --short HEAD          # same as step 1
ls "$HOME/src/ITKPythonPackage-build"/dist/*.whl  # expect 8 wheels
```

Every wheel should be named `*-cp311-abi3-macosx_26_0_arm64.whl`. Check
that a real binary agrees with the tag, because a wheel tagged below its
true minimum installs on older macOS and then fails at import:

```bash
unzip -qq -o <a-wheel>.whl -d /tmp/whlcheck
otool -l /tmp/whlcheck/itk/*.so | awk '/minos/{print $2; exit}'   # 26.0
```

**Warn the requester about the consequence:** wheels built with
`--macosx-deployment-target 26.0` run only on macOS 26 and newer, and
`-march=native` produces binaries tied to the building machine's CPU.
Both are correct for local testing and wrong for anything distributed.
The repository default is 14.0; see the platform policy below.

## Wheel platform policy (ITK 6)

These are decisions, not defaults to re-weigh. A change that breaks one
of them needs to say so explicitly.

1. **macOS is Apple Silicon (arm64) only.** Intel is dropped. The
   default `MACOSX_DEPLOYMENT_TARGET` is **14.0**: the lowest macOS
   still receiving security updates, and low enough that no Apple
   Silicon hardware is excluded. It is not the lowest arm64 supports
   (that is 11.0). The wheel tag must match the target, and
   `_PYTHON_HOST_PLATFORM` is derived from it so the two cannot drift.
   A component wheel tagged below its real minimum installs on older
   macOS and then fails in dyld at import.
2. **Python 3.11 is the minimum.** Do not add 3.9 or 3.10 targets.
3. **Linux is exactly manylinux_2_28.** manylinux2014 is dropped.
   `auditwheel repair` runs with `--only-plat`, so each wheel carries
   exactly one platform tag. Do not relax that flag to widen
   compatibility; fix the toolchain instead.
4. **Stable ABI (`abi3`) wheels only.** One `cp311-abi3` wheel per
   platform, via `wheel.py-api=cp311`. Never per-version `cp312`,
   `cp313`, ... wheels.

Together these give one wheel per platform:

| Platform       | Wheel tag                           |
| -------------- | ----------------------------------- |
| Linux x86_64   | `cp311-abi3-manylinux_2_28_x86_64`  |
| Linux aarch64  | `cp311-abi3-manylinux_2_28_aarch64` |
| macOS arm64    | `cp311-abi3-macosx_14_0_arm64`      |
| Windows x86_64 | `cp311-abi3-win_amd64`              |

A local test build may override the macOS target (see the worked
example above), but such wheels are not distributable.

## Related repositories

- [ITKPythonBuilds](https://github.com/InsightSoftwareConsortium/ITKPythonBuilds)
  hosts the cached ITK build tarballs.
- [ITKRemoteModuleBuildTestPackageAction](https://github.com/InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction)
  provides the reusable workflows remote modules call. Its macOS policy
  must agree with this repository's.

## Every command line argument

`scripts/build_wheels.py` accepts the following. Anything not listed is
not a real flag; do not invent one.

**Selecting the environment and source**

| Argument                    | Meaning                                         |
| --------------------------- | ----------------------------------------------- |
| `--platform-env NAME`       | Build environment; see the table above          |
| `--itk-source-dir PATH`     | Existing ITK checkout to reuse                  |
| `--itk-git-tag TAG`         | Tag, branch, or hash to check out               |
| `--itk-package-version VER` | PEP 440 version for the wheels                  |
| `--build-dir-root PATH`     | Build root; default `../ITKPythonPackage-build` |

**Platform options**

| Argument                         | Meaning                                         |
| -------------------------------- | ----------------------------------------------- |
| `--macosx-deployment-target VER` | macOS floor and wheel tag                       |
| `--manylinux-version VER`        | `_2_28`, `_2_34`; empty builds native Linux     |
| `--lib-paths DIRS`               | Windows only; `;`-delimited dirs for delvewheel |
| `--exclude-libs DLLS`            | Windows only; `;`-delimited DLLs not to bundle  |

**Remote modules**

| Argument                              | Meaning                           |
| ------------------------------------- | --------------------------------- |
| `--module-source-dir PATH`            | Remote module to build            |
| `--module-dependencies-root-dir PATH` | Where module deps are cloned      |
| `--itk-module-deps SPEC`              | `gitorg/repo@tag:gitorg/repo@tag` |

**Toggles**: each has a `--no-` counterpart:
`--build-itk-tarball-cache`, `--use-ccache`, `--dead-strip` (Linux and
macOS, on by default), `--skip-itk-build`, `--skip-itk-wheel-build`. Also `--cleanup`.

**Positional**: CMake definitions after the flags go to CMake unchanged,
for example `-DBUILD_SHARED_LIBS:BOOL=OFF`. These override defaults.
Anything that is not a `-D<KEY>=<VALUE>` definition is refused.

## Ingested remote modules

Modules that moved from remote modules into the ITK tree are marked
`EXCLUDE_FROM_DEFAULT` there. The wheels ship them:
`ITK_INGESTED_REMOTE_MODULES` in `scripts/build_python_instance_base.py`
turns each on. When ITK ingests another module, add it to that tuple. A
positional `-DModule_<name>:BOOL=OFF` overrides one.

Which wheel a module lands in follows from its ITK group and its
dependees; see `cmake/ITKPythonPackage_BuildWheels.cmake`. No wheel may
exceed PyPI's 100 MB limit on any platform; Linux x86_64 is the largest,
and the build fails before the import test when a wheel is over. To
rebalance, list modules in an `ITK_WHEEL_<group>_MODULE_OVERRIDES`
variable in that file. `itk-filtering-extra` exists for this reason: it
holds the ingested filtering modules, which would otherwise take
`itk-filtering` to 148 MB.

## Build steps and what skipping them means

The driver runs numbered steps and records which completed. The two
skip flags exist for reusing a previous build:

- `--skip-itk-build` skips the ITK C++ build (step 2).
- `--skip-itk-wheel-build` skips the ITK wheel build (step 3).

When wheels were never built, the later import test has nothing to
import and is skipped rather than failing. That is intended; do not
"fix" it by forcing the step.

## Testing your changes

```bash
pixi run -e dev python -m pytest tests/ -q     # unit tests
pixi run pre-commit run --all-files            # must exit 0
```

`pytest` is a developer-only dependency. Never make the normal build
path import it.

## Conventions

- Commit subjects use ITK prefixes (`BUG:`, `COMP:`, `DOC:`, `ENH:`,
  `PERF:`, `STYLE:`), at most 78 characters.
- Never add AI attribution to commit messages. `Co-Authored-By` is for
  human contributors.
- Never push a branch whose tip fails `pre-commit run --all-files`.
