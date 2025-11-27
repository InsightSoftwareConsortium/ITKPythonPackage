#!/usr/bin/env python3
"""
Generate build/package.env in a cross-platform way, rewriting the logic of
generate_build_environment.sh in Python.

Priority of settings (highest to lowest):
  1. Trailing KEY=VALUE pairs on the command line
  2. Mappings specified in -i input_file
  3. Exported environment variables from the current process
  4. Guessed values (computed defaults)

Usage:
  python generate_build_environment.py [-i input_file] [-o output_file] [KEY=VALUE ...]

Notes:
  - The resulting environment is written to build/package.env by default.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple


def debug(msg: str) -> None:
    print(msg)


def run(
    cmd: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, check=check, capture_output=True, text=True
    )


def which_required(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"MISSING: {name} not found in PATH; aborting until required executables can be found"
        )
    return path


def parse_kv_overrides(pairs: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for kv in pairs:
        if "=" not in kv:
            raise SystemExit(f"ERROR: Trailing argument '{kv}' is not KEY=VALUE")
        key, value = kv.split("=", 1)
        if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            raise SystemExit(f"ERROR: Invalid variable name '{key}' in '{kv}'")
        if value == "UNSET":
            # Explicitly remove if present later
            result[key] = None  # type: ignore
        else:
            result[key] = value
    return result


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        env[k] = v
    return env


def get_git_id(repo_dir: Path) -> str:
    # 1. exact tag
    try:
        tag = run(
            ["git", "describe", "--tags", "--exact-match"], cwd=repo_dir
        ).stdout.strip()
        if tag:
            return tag
    except subprocess.CalledProcessError:
        pass
    # 2. branch
    try:
        branch = run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir
        ).stdout.strip()
        if branch and branch != "HEAD":
            return branch
    except subprocess.CalledProcessError:
        pass
    # 3. short hash
    return run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir).stdout.strip()


def compute_itk_package_version(
    itk_dir: Path, itk_git_tag: str, ipp_latest_tag: str
) -> str:
    # Try to compute from git describe
    try:
        run(["git", "fetch", "--tags"], cwd=itk_dir)
        try:
            run(["git", "checkout", itk_git_tag], cwd=itk_dir)
        except Exception as e:
            print(
                f"WARNING: Failed to checkout {itk_git_tag}, reverting to 'main': {e}"
            )
            itk_git_tag = "main"
            run(["git", "checkout", itk_git_tag], cwd=itk_dir)
        desc = run(
            ["git", "describe", "--tags", "--long", "--dirty", "--always"], cwd=itk_dir
        ).stdout.strip()
        # Transform like sed -E 's/^([^-]+)-([0-9]+)-g([0-9a-f]+)(-dirty)?$/\1-dev.\2+\3\4/'
        m = re.match(r"^([^-]+)-([0-9]+)-g([0-9a-f]+)(-dirty)?$", desc)
        if m:
            base, commits, sha, dirty = m.groups()
            version = f"{base}-dev.{commits}+{sha}{dirty or ''}"
        else:
            version = desc
        # remove leading v
        if version.startswith("v"):
            version = version[1:]
    except subprocess.CalledProcessError:
        version = itk_git_tag.lstrip("v")

    # backward compatibility
    if itk_git_tag.lstrip("v") == ipp_latest_tag.lstrip("v"):
        version = itk_git_tag.lstrip("v")
    return version


def detect_platform() -> tuple[str, str]:
    # returns (os_name, arch)
    uname = os.uname() if hasattr(os, "uname") else None
    sysname = (
        uname.sysname if uname else ("Windows" if os.name == "nt" else sys.platform)
    )
    machine = (
        uname.machine
        if uname
        else (os.environ.get("PROCESSOR_ARCHITECTURE", "").lower())
    )
    os_name = (
        "linux"
        if sysname.lower().startswith("linux")
        else (
            "darwin"
            if sysname.lower().startswith("darwin") or sys.platform == "darwin"
            else ("windows" if os.name == "nt" else "unknown")
        )
    )
    # Normalize machine
    arch = machine
    if os_name == "darwin":
        if machine in ("x86_64",):
            arch = "x64"
        elif machine in ("arm64", "aarch64"):
            arch = "arm64"
    elif os_name == "linux":
        if machine in ("x86_64",):
            arch = "x64"
        elif machine in ("i686", "i386"):
            arch = "x86"
        elif machine in ("aarch64",):
            arch = "aarch64"
    return os_name, arch


def default_manylinux(
    os_name: str, arch: str, env: dict[str, str]
) -> tuple[str, str, str, str]:
    manylinux_version = env.get("MANYLINUX_VERSION", "_2_28")
    image_tag = env.get("IMAGE_TAG", "")
    container_source = env.get("CONTAINER_SOURCE", "")
    image_name = env.get("MANYLINUX_IMAGE_NAME", "")

    if os_name == "linux":
        if arch == "x64" and manylinux_version == "_2_34":
            image_tag = image_tag or "latest"
        elif arch == "x64" and manylinux_version == "_2_28":
            image_tag = image_tag or "20250913-6ea98ba"
        elif arch == "aarch64" and manylinux_version == "_2_28":
            image_tag = image_tag or "2025.08.12-1"
        elif manylinux_version == "2014":
            image_tag = image_tag or "20240304-9e57d2b"
        else:
            raise RuntimeError(
                f"FAILURE: Unknown manylinux version {manylinux_version}"
            )

        if arch == "x64":
            image_name = (
                image_name or f"manylinux{manylinux_version}-{arch}:{image_tag}"
            )
            container_source = container_source or f"docker.io/dockcross/{image_name}"
        elif arch == "aarch64":
            image_name = (
                image_name or f"manylinux{manylinux_version}_{arch}:{image_tag}"
            )
            container_source = container_source or f"quay.io/pypa/{image_name}"
        else:
            raise RuntimeError(f"Unknown target architecture {arch}")

    return manylinux_version, image_tag, image_name, container_source


def resolve_oci_exe(env: dict[str, str]) -> str:
    # Mirror scripts/oci_exe.sh best-effort by picking an available OCI tool.
    if env.get("OCI_EXE"):
        return env["OCI_EXE"]
    for cand in ("docker", "podman", "nerdctl"):
        if shutil.which(cand):
            return cand
    # Default to docker name if nothing found
    return "docker"


def cmake_compiler_defaults(build_dir: Path) -> tuple[str | None, str | None]:
    info = build_dir / "cmake_system_information"
    if not info.exists():
        try:
            out = run(["cmake", "--system-information"]).stdout
            info.write_text(out, encoding="utf-8")
        except Exception as e:
            print(f"WARNING: Failed to generate cmake_system_information: {e}")
            return None, None
    text = info.read_text(encoding="utf-8", errors="ignore")
    cc = None
    cxx = None
    for line in text.splitlines():
        if "CMAKE_C_COMPILER == " in line:
            parts = re.split(r"\s+", line.strip())
            if len(parts) >= 4:
                cc = parts[3]
        if "CMAKE_CXX_COMPILER == " in line:
            parts = re.split(r"\s+", line.strip())
            if len(parts) >= 4:
                cxx = parts[3]
    return cc, cxx


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("pairs", nargs="*")
    parser.add_argument("-i", dest="input_file", default=None)
    parser.add_argument("-o", dest="output_file", default=None)
    parser.add_argument("-h", action="store_true")
    args = parser.parse_args(argv)

    if args.h:
        print(
            "Usage:\nexport KEY0=VALUE0\npython generate_build_environment.py [-i input_file] [-o output_file] [KEY1=VALUE1  KEY2=VALUE2 ...]\nPRIORITY OF SETTING VALUES\n   lowest 0: guessed values not declared elsewhere\n          1: exported environmental variables. i.e. KEY0\n          2: mappings specified in input_file mappings\n  highest 3: mappings given at the end of the command line. i.e. KEY1, KEY2"
        )
        return 0

    repo_root = Path(__file__).resolve().parent
    _ipp_dir = repo_root
    build_dir = _ipp_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    build_env_report = args.output_file or str(build_dir / "package.env")
    ref_env_report_default = (
        build_env_report if Path(build_env_report).exists() else None
    )
    reference_env_report = args.input_file or ref_env_report_default

    debug(f"Input:   {reference_env_report or '<none>'}")
    debug(f"Output:  {build_env_report or '<none>'}")

    # If input == output and exists, backup
    if (
        reference_env_report
        and reference_env_report == build_env_report
        and Path(build_env_report).exists()
    ):
        backup = f"{build_env_report}_{Path(build_env_report).stat().st_mtime:.0f}"
        debug(f"{build_env_report} exists, backing up to {backup}")
        shutil.copyfile(build_env_report, backup)

    # Merge environments per priority
    env: dict[str, str] = dict(os.environ)
    if reference_env_report:
        env_from_file = load_env_file(Path(reference_env_report))
        env.update(env_from_file)  # priority 2 over 1
    overrides = parse_kv_overrides(args.pairs)
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v

    # Platform detection
    os_name, arch = detect_platform()

    # Required executables (paths recorded)
    doxygen_exec = env.get("DOXYGEN_EXECUTABLE") or which_required("doxygen")
    ninja_exec = env.get("NINJA_EXECUTABLE") or which_required("ninja")
    cmake_exec = env.get("CMAKE_EXECUTABLE") or which_required("cmake")

    # ITK repo handling
    itk_source_dir = Path(
        env.get("ITK_SOURCE_DIR", str(_ipp_dir / "ITK-source" / "ITK"))
    )
    ipp_latest_tag = get_git_id(_ipp_dir)
    ipp_latest_pep440 = (
        ipp_latest_tag[1:] if ipp_latest_tag.startswith("v") else ipp_latest_tag
    )

    itk_git_tag = env.get("ITK_GIT_TAG", ipp_latest_tag)
    if not itk_source_dir.exists():
        itk_source_dir.parent.mkdir(parents=True, exist_ok=True)
        debug(f"Cloning ITK into {itk_source_dir}...")
        run(
            [
                "git",
                "clone",
                "https://github.com/InsightSoftwareConsortium/ITK.git",
                str(itk_source_dir),
            ]
        )

    run(["git", "fetch", "--tags", "origin"], cwd=itk_source_dir)
    try:
        run(["git", "checkout", itk_git_tag], cwd=itk_source_dir)
    except subprocess.CalledProcessError:
        # try fetch then checkout
        print(f"WARNING: Failed to checkout {itk_git_tag}, reverting to 'main':")
        itk_git_tag = main
        run(["git", "checkout", itk_git_tag], cwd=itk_source_dir)

    itk_package_version = env.get("ITK_PACKAGE_VERSION") or compute_itk_package_version(
        itk_source_dir, itk_git_tag, ipp_latest_tag
    )

    # Manylinux/docker bits for Linux
    manylinux_version = env.get("MANYLINUX_VERSION", "_2_28")
    image_tag = env.get("IMAGE_TAG", "")
    manylinux_image_name = env.get("MANYLINUX_IMAGE_NAME", "")
    container_source = env.get("CONTAINER_SOURCE", "")
    target_arch = env.get("TARGET_ARCH") or arch

    if os_name == "linux":
        manylinux_version, image_tag, manylinux_image_name, container_source = (
            default_manylinux(os_name, target_arch, env)
        )
        oci_exe = resolve_oci_exe(env)
    else:
        oci_exe = env.get("OCI_EXE", "")

    # On macOS, compute CC_DEFAULT/CXX_DEFAULT if CC/CXX unset
    cc_default = None
    cxx_default = None
    if os_name == "darwin":
        if not env.get("CC") or not env.get("CXX"):
            cc_default, cxx_default = cmake_compiler_defaults(build_dir)

    # ITKPythonPackage origin/tag
    itkpp_org = env.get("ITKPYTHONPACKAGE_ORG", "InsightSoftwareConsortium")
    itkpp_tag = env.get("ITKPYTHONPACKAGE_TAG", ipp_latest_tag)

    # NO_SUDO, ITK_MODULE_NO_CLEANUP, USE_CCACHE
    no_sudo = env.get("NO_SUDO", "0")
    module_no_cleanup = env.get("ITK_MODULE_NO_CLEANUP", "1")
    use_ccache = env.get("USE_CCACHE", "0")
    itk_module_preq = env.get("ITK_MODULE_PREQ", "")

    # Write out package.env
    out_path = Path(build_env_report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    lines += [
        "################################################",
        "################################################",
        "###  ITKPythonPackage Environment Variables  ###",
        "###  in .env format (KEY=VALUE)              ###",
        "",
        "# - 'ITK_GIT_TAG': Tag/branch/hash for ITKPythonBuilds build cache to use",
        "#   Which ITK git tag/hash/branch to use as reference for building wheels/modules",
        "#   https://github.com/InsightSoftwareConsortium/ITK.git@${ITK_GIT_TAG}",
        "#   Examples: v5.4.0, v5.2.1.post1, 0ffcaed12552, my-testing-branch",
        "#   See available release tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags",
        f"ITK_GIT_TAG={itk_git_tag}",
        "",
        "# - 'ITK_SOURCE_DIR':  When building different 'flavor' of ITK python packages",
        "#   on a given platform, explicitly setting the ITK_SOURCE_DIR options allow to",
        "#   speed up source-code downloads by re-using an existing repository.",
        "#   If the requested directory does not exist, manually clone and checkout ${ITK_GIT_TAG}",
        f"ITK_SOURCE_DIR={itk_source_dir}",
        "",
        "# - 'ITK_PACKAGE_VERSION' A valid PEP440 python version string.  This should be ITK_GIT_TAG without",
        "#   the preceding 'v' for tagged releases.",
        "#   The default is to have a temporary version automatically created from based on relative",
        "#   versioning from the latest tagged release.",
        "#   (in github action ITKRemoteModuleBuildTestPackage itk-wheel-tag is used to set this value)",
        f"ITK_PACKAGE_VERSION={itk_package_version}",
        "",
        "# - 'ITKPYTHONPACKAGE_ORG':Github organization or user to use for ITKPythonPackage build scripts",
        "#   Which script version to use in generating python packages",
        "#   https://github.com/InsightSoftwareConsortium/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git@${ITKPYTHONPACKAGE_TAG}",
        "#   build script source. Default is InsightSoftwareConsortium.",
        "#   Ignored if ITKPYTHONPACKAGE_TAG is empty.",
        "#   (in github action ITKRemoteModuleBuildTestPackage itk-python-package-org is used to set this value)",
        f"ITKPYTHONPACKAGE_ORG={itkpp_org}",
        "",
        "# - 'ITKPYTHONPACKAGE_TAG': Tag for ITKPythonPackage build scripts to use.",
        "#   If ITKPYTHONPACKAGE_TAG is empty then the default scripts distributed",
        "#   with the ITKPythonBuilds archive will be used.",
        "#   (in github action ITKRemoteModuleBuildTestPackage itk-python-package-tag is used to set this value)",
        f"ITKPYTHONPACKAGE_TAG={itkpp_tag}",
        "",
        "# - 'ITK_MODULE_PREQ': Prerequisite ITK modules that must be built before the requested module.",
        "#   Format is '<org_name>/<module_name>@<module_tag>:<org_name>/<module_name>@<module_tag>:...''.",
        "#   For instance, 'export ITK_MODULE_PREQ=InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0'",
        "#   See notes in 'dockcross-manylinux-build-module-deps.sh'.",
        "#   (in github action ITKRemoteModuleBuildTestPackage itk-module-deps is used to set this value)",
        f"ITK_MODULE_PREQ={itk_module_preq}",
        "",
        "# - 'NO_SUDO': Disable if running docker does not require sudo priveleges",
        "#   (set to 1 if your user account can run docker, set to 0 otherwise).",
        f"NO_SUDO={no_sudo}",
        "",
        "# - 'ITK_MODULE_NO_CLEANUP': Option to skip cleanup steps.",
        "#   =1 <- Leave tempoary build files in place after completion, 0 <- remove temporary build files",
        f"ITK_MODULE_NO_CLEANUP={module_no_cleanup}",
        "",
        "# - 'USE_CCACHE': Option to indicate that ccache should be used",
        "#   =1 <- Set cmake settings to use ccache for acclerating rebuilds, 0 <- no ccache usage",
        f"USE_CCACHE={use_ccache}",
        f"DOXYGEN_EXECUTABLE={doxygen_exec}",
        f"NINJA_EXECUTABLE={ninja_exec}",
        f"CMAKE_EXECUTABLE={cmake_exec}",
    ]

    if os_name == "linux":
        ld_library_path = env.get("LD_LIBRARY_PATH", "")
        lines += [
            "",
            "# Linux / dockcross settings",
            f"OCI_EXE={oci_exe}",
            f"MANYLINUX_VERSION={manylinux_version}",
            f"TARGET_ARCH={target_arch}",
            f"IMAGE_TAG={image_tag}",
            f"LD_LIBRARY_PATH={ld_library_path}",
            f"MANYLINUX_IMAGE_NAME={manylinux_image_name}",
            f"CONTAINER_SOURCE={container_source}",
        ]

    if os_name == "darwin":
        # Standard build flags that may be present
        build_vars = [
            "CC",
            "CXX",
            "FC",
            "CFLAGS",
            "CXXFLAGS",
            "FFLAGS",
            "CPPFLAGS",
            "LDFLAGS",
            "SDKROOT",
            "MACOSX_DEPLOYMENT_TARGET",
            "PKG_CONFIG_PATH",
            "PKG_CONFIG_LIBDIR",
            "LD_LIBRARY_PATH",
            "DYLD_LIBRARY_PATH",
        ]
        lines += [
            "",
            "# Standard environmental build flags respected by cmake and other build tools ",
            "# Autogenerated build environment",
            "# Source this file before builds",
        ]
        # Include CC_DEFAULT/CXX_DEFAULT hints
        if cc_default:
            lines.append(f"CC_DEFAULT={cc_default}")
        else:
            lines.append("## - CC_DEFAULT=")
        if cxx_default:
            lines.append(f"CXX_DEFAULT={cxx_default}")
        else:
            lines.append("## - CXX_DEFAULT=")
        for var in build_vars:
            val = env.get(var, "")
            if val:
                lines.append(f"{var}={val}")
            else:
                lines.append(f"## - {var}=")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Print the generated file content (parity with bash script)
    print(out_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
