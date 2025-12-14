#!/usr/bin/env python3
"""
Generate .env formatted file with build parameters build/package.env in a cross-platform way

Priority of settings (highest to lowest):
  1. Trailing KEY=VALUE pairs on the command line (always retained)
  2. Mappings specified in -i input_file
  3. Exported environment variables from the current process
  4. Guessed values (computed defaults, last resort for setting values)

Usage:
  export KEY0=VALUE0; python generate_build_environment.py [-i input_file] [-o output_file] [KEY1=VALUE1 KEY2=VALUE2 ...]

Notes:
  - The resulting environment is written to the output_file if specified or build/package.env by default.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from wheel_builder_utils import detect_platform, which_required


def git_describe_to_pep440(desc: str) -> str:
    """
    Convert `git describe --tags --long --dirty --always` output

    # v6.0b03-3-g1a2b3c4
    # │   |   │   └── abbreviated commit hash
    # │   |   └────── commits since tag
    # |   └────────── pre-release type and number
    # └────────────── nearest tag
    to a PEP 440–compatible version string.

    [N!]N(.N)*[{a|b|rc}N][.postN][.devN]+<localinfo>
    111122222233333333333444444445555555666666666666
    1 Epoch segment: N!
    2 Release segment: N(.N)*
    3 Pre-release segment: {a|b|rc}N
    4 Post-release segment: .postN
    5 Development release segment: .devN
    6 local info not used in version ordering. I.e. ignored by package resolution rules
    """
    desc = desc.strip()
    dirty = False
    semver_format = "0.0.0"

    m = re.match(
        r"^(v)*(?P<majorver>\d+)(?P<minor>\.\d+)(?P<patch>\.\d+)*(?P<pretype>a|b|rc|alpha|beta)*0*(?P<prerelnum>\d*)-*(?P<posttagcount>\d*)-*g*(?P<sha>[0-9a-fA-F]+)*(?P<dirty>.dirty)*$",
        desc,
    )
    if m:
        groupdict = m.groupdict()

        semver_format = (
            f"{groupdict.get('majorver','')}" + f"{groupdict.get('minor','')}"
        )
        patch = groupdict.get("patch", None)
        if patch:
            semver_format += f"{patch}"
        else:
            semver_format += ".0"

        prereleasemapping = {
            "alpha": "a",
            "a": "a",
            "beta": "b",
            "b": "b",
            "rc": "rc",
            "": "",
        }
        prerelease_name = prereleasemapping.get(groupdict.get("pretype", ""), None)
        prerelnum = groupdict.get("prerelnum", None)
        if prerelease_name and prerelnum and len(prerelease_name) > 0:
            semver_format += f"{prerelease_name}{prerelnum}"
        posttagcount = groupdict.get("posttagcount", None)
        dirty = groupdict.get("dirty", None)
        if len(posttagcount) > 0 and int(posttagcount) == 0 and (dirty is None or len(dirty) == 0):
            # If exactly on a tag, then do not add post, or sha
            return semver_format
        else:
            if posttagcount and int(posttagcount) > 0:
                semver_format += f".post{posttagcount}"
            sha = groupdict.get("sha", None)
            if sha:
                semver_format += f"+g{sha.lower()}"
            if dirty:
                semver_format += f".dirty"
    return semver_format


def debug(msg: str, do_print=False) -> None:
    if do_print:
        print(msg)


def run(
    cmd: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess:
    print(f"Running >>>>>: {' '.join(cmd)}  ; # in cwd={cwd} with check={check}")
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, check=check, capture_output=True, text=True
    )


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


def get_git_id(repo_dir: Path, backup_version: str = "v0.0.0") -> str:
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
    try:
        short_version = run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir
        ).stdout.strip()
        if short_version and short_version != "HEAD":
            return short_version
    except subprocess.CalledProcessError:
        pass

    # 4. punt and give dummy backup_version identifier
    if not (repo_dir / ".git").is_dir():
        if (repo_dir / ".git").is_file():
            print(
                f"WARNING: {str(repo_dir)} is a secondary git worktree, and may not resolve from within dockercross build"
            )
            return backup_version
        print(f"ERROR: {repo_dir} is not a primary git repository")
        return backup_version


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
        version = git_describe_to_pep440(desc)
    except subprocess.CalledProcessError:
        version = itk_git_tag.lstrip("v")

    return version


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
        elif manylinux_version == "":
            image_tag = ""
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
        if shutil.which(cand):  # NOTE ALWAYS RETURNS NONE ON WINDOWS
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


def generate_build_environment(argv: list[str]) -> int:
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

    _ipp_dir = Path(__file__).resolve().parent.parent
    build_dir = _ipp_dir / "build"
    build_env_report = args.output_file or str(build_dir / "package.env")

    if args.input_file:
        reference_env_report = args.input_file
    else:
        build_dir.mkdir(parents=True, exist_ok=True)
        reference_env_report = (
            build_env_report if Path(build_env_report).exists() else None
        )
    if reference_env_report:
        reference_env_report = Path(reference_env_report)

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
        env_from_file.update(
            env
        )  # Environmental settings override matching env_from_file settings
        env.update(env_from_file)  # Merge extra env_from_file settings back into env
    overrides = parse_kv_overrides(args.pairs)
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v

    # Platform detection
    os_name, arch = detect_platform()

    # Required executables (paths recorded)

    doxygen_exec = env.get("DOXYGEN_EXECUTABLE", None)
    ninja_exec = env.get("NINJA_EXECUTABLE", None)
    cmake_exec = env.get("CMAKE_EXECUTABLE", None)

    if doxygen_exec is None or ninja_exec is None or cmake_exec is None:
        print("Generating pixi installed resources.")
        build_dir.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "curl",
                "-fsSL",
                "https://pixi.sh/install.sh",
                "-o",
                str(build_dir.parent / "pixi_install.sh"),
            ]
        )
        pixi_home = _ipp_dir / ".pixi"
        pixi_home.mkdir(parents=True, exist_ok=True)
        os.environ["PIXI_HOME"] = str(pixi_home)
        pixi_install_dir = pixi_home / "bin"
        run(
            [
                "/bin/sh",
                str(build_dir.parent / "pixi_install.sh"),
            ]
        )
        run(
            [
                str(pixi_install_dir / "pixi"),
                "global",
                "install",
                "doxygen",
                "cmake",
                "ninja",
                "patchelf",
            ]
        )
        os.environ["PATH"] = (
            str(pixi_install_dir) + os.pathsep + os.environ.get("PATH", "")
        )

    doxygen_exec = which_required("doxygen")
    ninja_exec = which_required("ninja")
    cmake_exec = which_required("cmake")

    ipp_latest_tag: str = get_git_id(
        _ipp_dir, env.get("ITKPYTHONPACKAGE_TAG", "v0.0.0")
    )
    # semver_from_tag: str = (
    #    ipp_latest_tag[1:] if ipp_latest_tag.startswith("v") else ipp_latest_tag
    # )
    # pep440_tag: str = semver_to_pep440(semver_from_tag)

    itk_git_tag = env.get("ITK_GIT_TAG", ipp_latest_tag)
    # ITK repo handling
    itk_source_dir = Path(
        env.get("ITK_SOURCE_DIR", str(_ipp_dir / "ITK-source" / "ITK"))
    )
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
        itk_git_tag = "main"
        run(["git", "checkout", itk_git_tag], cwd=itk_source_dir)

    itk_package_version = env.get(
        "ITK_PACKAGE_VERSION",
        compute_itk_package_version(itk_source_dir, itk_git_tag, ipp_latest_tag),
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
        tbb_dir = env.get("TBB_DIR", None)
        if tbb_dir:
            lines += [f"TBB_DIR={tbb_dir}"]

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
    sys.exit(generate_build_environment(sys.argv[1:]))
