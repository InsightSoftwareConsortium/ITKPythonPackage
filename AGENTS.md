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

| Platform | `--platform-env` |
|---|---|
| macOS arm64 | `macosx-py311` |
| Linux x86_64 / aarch64 native | `linux-py311` |
| Linux via manylinux container | `manylinux228-py311` |
| Windows x86_64 | `windows-py311` |

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


## Worked example

> "Build Python packages on my Mac only, with `-mtune=native
> -march=native` and macOS 26, for PR 6875 which is not merged yet, so I
> can test it in my environment."

Four things are being asked for: a local macOS build, custom compiler
flags, a non-default deployment target, and ITK source from an unmerged
pull request. Do them in this order.

**Step 1 — get the PR source.** The build script runs `git fetch --tags
origin` and then `git checkout <tag>`. It does **not** fetch
`pull/N/head` refs, so a pull request ref must be fetched by hand first.

```bash
ITK_SRC="$HOME/src/ITK"
git -C "$ITK_SRC" fetch origin pull/6875/head:pr-6875
git -C "$ITK_SRC" checkout pr-6875
git -C "$ITK_SRC" rev-parse --short HEAD     # record this
```

**Step 2 — build.** Positional arguments after the flags are passed
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

**Step 3 — verify you built what was asked for.** A failed checkout in
step 1 prints a warning and keeps whatever commit was already there, so
confirm the source and the resulting tag rather than assuming:

```bash
git -C "$ITK_SRC" rev-parse --short HEAD          # same as step 1
ls "$HOME/src/ITKPythonPackage-build"/dist/*.whl  # expect 7 wheels
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

| Platform | Wheel tag |
|---|---|
| Linux x86_64 | `cp311-abi3-manylinux_2_28_x86_64` |
| Linux aarch64 | `cp311-abi3-manylinux_2_28_aarch64` |
| macOS arm64 | `cp311-abi3-macosx_14_0_arm64` |
| Windows x86_64 | `cp311-abi3-win_amd64` |

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

| Argument | Meaning |
|---|---|
| `--platform-env NAME` | Build environment; see the table above |
| `--itk-source-dir PATH` | Existing ITK checkout to reuse |
| `--itk-git-tag TAG` | Tag, branch, or hash to check out |
| `--itk-package-version VER` | PEP 440 version for the wheels |
| `--build-dir-root PATH` | Build root; default `../ITKPythonPackage-build` |

**Platform options**

| Argument | Meaning |
|---|---|
| `--macosx-deployment-target VER` | macOS floor and wheel tag |
| `--manylinux-version VER` | `_2_28`, `_2_34`; empty builds native Linux |
| `--lib-paths DIRS` | Windows only; `;`-delimited dirs for delvewheel |

**Remote modules**

| Argument | Meaning |
|---|---|
| `--module-source-dir PATH` | Remote module to build |
| `--module-dependencies-root-dir PATH` | Where module deps are cloned |
| `--itk-module-deps SPEC` | `gitorg/repo@tag:gitorg/repo@tag` |

**Toggles** — each has a `--no-` counterpart:
`--build-itk-tarball-cache`, `--use-sudo`, `--use-ccache`,
`--skip-itk-build`, `--skip-itk-wheel-build`. Also `--cleanup`.

**Positional** — everything after the flags goes to CMake unchanged,
for example `-DBUILD_SHARED_LIBS:BOOL=OFF`. These override defaults.

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
