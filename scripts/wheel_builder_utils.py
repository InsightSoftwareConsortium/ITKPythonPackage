"""This module provides convenient function facilitating scripting.

These functions have been copied from scikit-build project.
See https://github.com/scikit-build/scikit-build
"""

from __future__ import (
    annotations,
)  # Needed for python 3.9 to support python 3.10 style typehints

import filecmp
import os
import re
import shutil
import subprocess
import sys

from pathlib import Path
from os import chdir as os_chdir, environ

# from contextlib import contextmanager
from functools import wraps

# @contextmanager
# def push_env(**kwargs):
#     """This context manager allow to set/unset environment variables."""
#     saved_env = dict(os_environ)
#     for var, value in kwargs.items():
#         if value is not None:
#             os_environ[var] = value
#         elif var in os_environ:
#             del os_environ[var]
#     yield
#     os_environ.clear()
#     for saved_var, saved_value in saved_env.items():
#         os_environ[saved_var] = saved_value


class ContextDecorator:
    """A base class or mixin that enables context managers to work as
    decorators."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __enter__(self):
        # Note: Returning self means that in "with ... as x", x will be self
        return self

    def __exit__(self, typ, val, traceback):
        pass

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwds):  # pylint:disable=missing-docstring
            with self:
                return func(*args, **kwds)

        return inner


class push_dir(ContextDecorator):
    """Context manager to change current directory."""

    def __init__(self, directory=None, make_directory=False):
        """
        :param directory:
          Path to set as current working directory. If ``None``
          is passed, current working directory is used instead.

        :param make_directory:
          If True, ``directory`` is created.
        """
        self.directory = None
        self.make_directory = None
        self.old_cwd = None
        super().__init__(directory=directory, make_directory=make_directory)

    def __enter__(self):
        self.old_cwd = Path.cwd()
        if self.directory:
            if self.make_directory:
                Path(self.directory).mkdir(parents=True, exist_ok=True)
            os_chdir(self.directory)
        return self

    def __exit__(self, typ, val, traceback):
        os_chdir(self.old_cwd)


def _remove_tree(path: Path) -> None:
    """Recursively delete a file or directory using pathlib only."""
    if not path.exists():
        return
    if path.is_file() or path.is_symlink():
        try:
            path.unlink()
        except OSError:
            pass
        return
    for child in path.iterdir():
        _remove_tree(child)
    try:
        path.rmdir()
    except OSError:
        pass


def read_env_file(
    file_path: os.PathLike | str, build_dir_root: os.PathLike | str
) -> dict[str, str]:
    """Read a simple .env-style file and return a dict of key/value pairs.

    Supported syntax:
    - Blank lines and lines starting with '#' are ignored.
    - Optional leading 'export ' prefix is ignored.
    - KEY=VALUE pairs; surrounding single or double quotes are stripped.
    - Whitespace around keys and the '=' is ignored.

    This function does not perform variable expansion or modify os.environ.
    """
    result: dict[str, str] = {}
    path = Path(file_path)
    if not path.exists():
        return result
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return result

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        value = value.replace("${BUILD_DIR_ROOT}", str(build_dir_root))
        # Strip surrounding quotes if present
        if (len(value) >= 2) and (
            (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
        ):
            value = value[1:-1]
        result[key] = value
    return result


def _which(exe_name: str) -> Path | None:
    """Simple PATH-based lookup using pathlib only."""
    # shutil.which only works on windows after python 3.12.
    pathext: list[str] = environ.get("PATHEXT", ".EXE;.BAT;.CMD;.exe;.bat;.cmd").split(
        ";"
    )
    paths: list[str] = environ.get("PATH", "").split(os.pathsep)
    exe: Path = Path(exe_name)
    candidates: list[Path] = (
        [exe] if exe.suffix else [Path(exe_name + ext) for ext in pathext]
    )
    candidates = [exe] + candidates
    for p in paths:
        if not p:
            continue
        base = Path(p)
        for c in candidates:
            fp = base / c
            try:
                if fp.exists():
                    return fp
            except OSError:
                continue
    return None


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


def which_required(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"MISSING: {name} not found in PATH; aborting until required executables can be found"
        )
    return path


def run_commandLine_subprocess(
    cmd: list[str | Path], cwd: Path | None = None, env: dict = None, check: bool = True
) -> subprocess.CompletedProcess:
    cmd = [str(x) for x in cmd]
    print(f"Running >>>>>: {' '.join(cmd)}  ; # in cwd={cwd} with check={check}\n")
    # if env:
    #     for k, v in env.items():
    #         print(f"{k}={v}")
    completion_info = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env if env else None,
    )
    if completion_info.returncode != 0 and check:
        error_msg = "!~" * 40
        if completion_info.stdout:
            error_msg += f"\nStdout:\n {completion_info.stdout}"
        if completion_info.stderr:
            error_msg += f"\nStderr:\n {completion_info.stderr}"
        error_msg += f"Command failed with exit code {completion_info.returncode}: {' '.join(cmd)}"

        raise RuntimeError(error_msg)

    return completion_info


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
        if (
            len(posttagcount) > 0
            and int(posttagcount) == 0
            and (dirty is None or len(dirty) == 0)
        ):
            # If exactly on a tag, then do not add post, or sha
            return semver_format
        else:
            if posttagcount and int(posttagcount) > 0:
                semver_format += f".post{posttagcount}"
            sha = groupdict.get("sha", None)
            if sha:
                semver_format += f"+g{sha.lower()}"
            if dirty:
                semver_format += ".dirty"
    return semver_format


def debug(msg: str, do_print=False) -> None:
    if do_print:
        print(msg)


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


def get_git_id(
    repo_dir: Path, pixi_exec_path, env, backup_version: str = "v0.0.0"
) -> str | None:
    # 1. exact tag
    try:
        run_result = run_commandLine_subprocess(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=repo_dir,
            env=env,
            check=False,
        )

        if run_result.returncode == 0:
            return run_result.stdout.strip()
    except subprocess.CalledProcessError:
        pass
    # 2. branch
    try:
        run_result = run_commandLine_subprocess(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir,
            env=env,
        )
        branch = run_result.stdout.strip()
        if run_result.returncode == 0 and branch != "HEAD":
            return branch
    except subprocess.CalledProcessError:
        pass
    # 3. short hash
    try:
        run_result = run_commandLine_subprocess(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir,
            env=env,
        )
        short_version = run_result.stdout.strip()
        if run_result.returncode == 0 and short_version != "HEAD":
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
    itk_dir: Path, itk_git_tag: str, pixi_exec_path, env
) -> str:
    # Try to compute from git describe
    try:
        run_commandLine_subprocess(
            ["git", "fetch", "--tags"],
            cwd=itk_dir,
            env=env,
        )
        try:
            run_commandLine_subprocess(
                ["git", "checkout", itk_git_tag],
                cwd=itk_dir,
                env=env,
            )
        except Exception as e:
            print(
                f"WARNING: Failed to checkout {itk_git_tag}, reverting to 'main': {e}"
            )
            itk_git_tag = "main"
            run_commandLine_subprocess(
                ["git", "checkout", itk_git_tag],
                cwd=itk_dir,
                env=env,
            )
        desc = run_commandLine_subprocess(
            [
                "git",
                "describe",
                "--tags",
                "--long",
                "--dirty",
                "--always",
            ],
            cwd=itk_dir,
            env=env,
        ).stdout.strip()
        version = git_describe_to_pep440(desc)
    except subprocess.CalledProcessError:
        version = itk_git_tag.lstrip("v")

    return version


def default_manylinux(
    manylinux_version: str, os_name: str, arch: str, env: dict[str, str]
) -> tuple[str, str, str]:
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

    return image_tag, image_name, container_source


def resolve_oci_exe(env: dict[str, str]) -> str:
    # Mirror scripts/oci_exe.sh best-effort by picking an available OCI tool.
    if env.get("OCI_EXE"):
        return env["OCI_EXE"]
    for cand in ("docker", "podman", "nerdctl"):
        if shutil.which(cand):  # NOTE ALWAYS RETURNS NONE ON WINDOWS before 3.12
            return cand
    # Default to docker name if nothing found
    return "docker"


# def cmake_compiler_defaults(build_dir: Path) -> tuple[str | None, str | None]:
#     info = build_dir / "cmake_system_information"
#     if not info.exists():
#         try:
#             out = run_commandLine_subprocess(["cmake", "--system-information"]).stdout
#             info.write_text(out, encoding="utf-8")
#         except Exception as e:
#             print(f"WARNING: Failed to generate cmake_system_information: {e}")
#             return None, None
#     text = info.read_text(encoding="utf-8", errors="ignore")
#     cc = None
#     cxx = None
#     for line in text.splitlines():
#         if "CMAKE_C_COMPILER == " in line:
#             parts = re.split(r"\s+", line.strip())
#             if len(parts) >= 4:
#                 cc = parts[3]
#         if "CMAKE_CXX_COMPILER == " in line:
#             parts = re.split(r"\s+", line.strip())
#             if len(parts) >= 4:
#                 cxx = parts[3]
#     return cc, cxx


def give_relative_path(bin_exec: Path, build_dir_root: Path) -> str:
    bin_exec = Path(bin_exec).resolve()
    build_dir_root = Path(build_dir_root).resolve()
    if bin_exec.is_relative_to(build_dir_root):
        return "${BUILD_DIR_ROOT}" + os.sep + str(bin_exec.relative_to(build_dir_root))
    return str(bin_exec)


def safe_copy_if_different(src: Path, dst: Path) -> None:
    """Copy file only if destination is missing or contents differ.

    This avoids unnecessary overwrites and timestamp churn when files are identical.
    """
    src = Path(src)
    dst = Path(dst)
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        return
    try:
        same = filecmp.cmp(src, dst, shallow=False)
    except Exception as e:
        # On any comparison failure, fall back to copying to be safe
        same = False
        print(f"WARNING: Failed to compare {src} to {dst}: {e}")
    if not same:
        shutil.copyfile(src, dst)
