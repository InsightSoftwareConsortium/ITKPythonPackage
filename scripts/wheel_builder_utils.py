"""This module provides convenient function facilitating scripting.

These functions have been copied from scikit-build project.
See https://github.com/scikit-build/scikit-build
"""

import filecmp
import os
import re
import shutil
import subprocess
import sys

# from contextlib import contextmanager
from functools import wraps
from os import chdir as os_chdir
from os import environ
from pathlib import Path


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
    """Recursively delete a file or directory using pathlib only.

    Parameters
    ----------
    path : Path
        File or directory to remove.  No error is raised if *path*
        does not exist.
    """
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

    - Blank lines and lines starting with ``#`` are ignored.
    - Optional leading ``export`` prefix is stripped.
    - ``KEY=VALUE`` pairs; surrounding single or double quotes are stripped.
    - Whitespace around keys and the ``=`` is ignored.
    - ``${BUILD_DIR_ROOT}`` in values is replaced with *build_dir_root*.

    This function does not perform variable expansion or modify ``os.environ``.

    Parameters
    ----------
    file_path : os.PathLike or str
        Path to the ``.env`` file.
    build_dir_root : os.PathLike or str
        Value substituted for ``${BUILD_DIR_ROOT}`` placeholders in values.

    Returns
    -------
    dict[str, str]
        Parsed key/value pairs.  Returns an empty dict if the file does
        not exist or cannot be read.
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
    """Locate an executable on ``PATH`` using pathlib.

    A custom implementation is used because ``shutil.which`` does not
    reliably resolve executables on Windows before Python 3.12.

    Parameters
    ----------
    exe_name : str
        Name (or path fragment) of the executable to find.

    Returns
    -------
    Path or None
        Absolute path to the first matching executable, or ``None`` if
        not found.
    """
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


HOST_SYSTEM_ENVIRONMENT_NAME = "hostsystem"
"""Opt out of pixi tool resolution and use the host system's PATH."""


def abort_if_wrong_pixi_environment(platform_env: str) -> None:
    """Fail immediately when launched outside the requested pixi environment.

    Raises
    ------
    SystemExit
        If the active environment is not *platform_env*.
    """
    active = os.environ.get("PIXI_ENVIRONMENT_NAME")
    if active in (platform_env, HOST_SYSTEM_ENVIRONMENT_NAME):
        return
    where = (
        f"the {active!r} pixi environment"
        if active
        else "no pixi environment (plain shell)"
    )
    sys.exit(
        "\n"
        "==============================================================\n"
        "  WRONG ENVIRONMENT - build aborted before doing any work\n"
        "==============================================================\n"
        f"  running in : {where}\n"
        f"  required   : {platform_env!r}\n"
        "\n"
        f"  Re-run with the environment selected:\n"
        f"      pixi run -e {platform_env} python scripts/build_wheels.py ...\n"
        "\n"
        "  'pixi run' without '-e' uses the 'default' environment, which\n"
        "  does NOT carry the pinned cmake, ninja, doxygen and git. The\n"
        "  build would silently pick up whatever is on the system PATH.\n"
        "\n"
        "  To deliberately build with host-system tools instead of pixi:\n"
        f"      PIXI_ENVIRONMENT_NAME={HOST_SYSTEM_ENVIRONMENT_NAME} python "
        "scripts/build_wheels.py ...\n"
        "=============================================================="
    )


def which_required_in_pixi_env(
    name: str, pixi_executable: Path, platform_env: str
) -> Path:
    """Locate a required executable inside a pixi environment.

    Returns
    -------
    Path
        Absolute path to the executable within *platform_env*.

    Raises
    ------
    RuntimeError
        If *name* is not resolvable inside *platform_env*.
    """
    if os.environ.get("PIXI_ENVIRONMENT_NAME") in (
        platform_env,
        HOST_SYSTEM_ENVIRONMENT_NAME,
    ):
        return which_required(name)
    probe = run_commandLine_subprocess(
        [
            pixi_executable,
            "run",
            "-e",
            platform_env,
            "python",
            "-c",
            f"import shutil; print(shutil.which({name!r}) or '')",
        ],
        env=os.environ.copy(),
    )
    resolved = probe.stdout.strip() if probe.returncode == 0 else ""
    if not resolved:
        raise RuntimeError(
            f"MISSING: {name} not found in pixi environment {platform_env!r}; "
            f"aborting until required executables can be found"
        )
    return Path(resolved)


def which_required(name: str) -> Path:
    """Locate a required executable, raising when it is absent.

    Returns
    -------
    Path
        Absolute path to the executable.

    Raises
    ------
    RuntimeError
        If *name* is not on ``PATH``.
    """
    path = _which(name)
    if not path:
        raise RuntimeError(
            f"MISSING: {name} not found in PATH; aborting until required executables can be found"
        )
    return path


def run_commandLine_subprocess(
    cmd: list[str | Path],
    cwd: Path | None = None,
    env: dict = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command via ``subprocess.run`` with logging.

    Parameters
    ----------
    cmd : list[str or Path]
        Command and arguments to execute.
    cwd : Path, optional
        Working directory for the subprocess.
    env : dict, optional
        Environment variables for the subprocess.
    check : bool, optional
        If True, raise ``RuntimeError`` on non-zero exit codes.

    Returns
    -------
    subprocess.CompletedProcess
        Completed process information including stdout, stderr, and
        return code.

    Raises
    ------
    RuntimeError
        If *check* is True and the command exits with a non-zero code.
    """
    cmd = [str(x) for x in cmd]
    print(f"Running >>>>>: {' '.join(cmd)}  ; # in cwd={cwd} with check={check}\n")
    completion_info = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env if env else None,
    )
    if completion_info.returncode != 0 and check:
        error_msg = "!~" * 40
        if env:
            error_msg += "ENVIRONMENT: ================="
            for k, v in env.items():
                error_msg += f"\n{k}={v}"
            error_msg += "=============================="
        if completion_info.stdout:
            error_msg += f"\nStdout:\n {completion_info.stdout}"
        if completion_info.stderr:
            error_msg += f"\nStderr:\n {completion_info.stderr}"
        error_msg += f"Command failed with exit code {completion_info.returncode}: {' '.join(cmd)}"
        print(error_msg)
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


def compute_itk_package_version(
    itk_dir: Path, itk_git_tag: str, pixi_exec_path, env
) -> str:
    """Compute a PEP 440 version string for the ITK package.

    Fetches tags, checks out *itk_git_tag*, and runs
    ``git describe --tags --long --dirty --always`` to produce a version
    via `git_describe_to_pep440`.

    Parameters
    ----------
    itk_dir : Path
        Path to the ITK source repository.
    itk_git_tag : str
        Git tag, branch, or commit to check out before describing.
    pixi_exec_path : Path or str
        Path to the pixi executable (unused but kept for API compat).
    env : dict
        Environment variables passed to Git subprocesses.

    Returns
    -------
    str
        PEP 440-compliant version string.
    """
    if (
        run_commandLine_subprocess(
            ["git", "rev-parse", "--git-dir"], cwd=itk_dir, env=env
        ).returncode
        != 0
    ):
        raise RuntimeError(
            f"Cannot derive a version from {itk_dir}: it is not a git "
            f"repository, which is how a source tree restored from a build "
            f"cache arrives. Pass --itk-package-version, or set "
            f"ITK_PACKAGE_VERSION, to name the version explicitly."
        )
    fetch_result = run_commandLine_subprocess(
        ["git", "fetch", "--tags"],
        cwd=itk_dir,
        env=env,
    )
    if fetch_result.returncode != 0:
        raise RuntimeError(
            f"git fetch --tags failed in {itk_dir}: {fetch_result.stderr}"
        )
    checkout_result = run_commandLine_subprocess(
        ["git", "checkout", itk_git_tag],
        cwd=itk_dir,
        env=env,
    )
    if checkout_result.returncode != 0:
        # Keep the commit already checked out; see the matching comment in
        # build_wheels.py. Forcing 'main' would move a cache-restored ITK
        # source tree away from the commit its prebuilt binaries were
        # compiled from.
        head_result = run_commandLine_subprocess(
            ["git", "rev-parse", "HEAD"],
            cwd=itk_dir,
            env=env,
        )
        resolved = head_result.stdout.strip() if head_result.returncode == 0 else ""
        print(
            f"WARNING: Failed to checkout {itk_git_tag}; keeping the commit "
            f"already checked out ({resolved or 'unknown'}): "
            f"{checkout_result.stderr}"
        )
        if resolved:
            itk_git_tag = resolved
    describe_result = run_commandLine_subprocess(
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
    )
    desc = describe_result.stdout.strip()
    if describe_result.returncode != 0 or not desc:
        raise RuntimeError(
            f"git describe produced no usable version in {itk_dir} "
            f"(exit status {describe_result.returncode}): "
            f"{describe_result.stderr}"
        )
    version = git_describe_to_pep440(desc)
    if version == "0.0.0":
        raise RuntimeError(
            f"git describe output {desc!r} does not yield an ITK version; "
            f"refusing to build wheels named 0.0.0"
        )

    return version


def resolve_oci_exe(env: dict[str, str]) -> str:
    """Find an OCI container runtime (docker, podman, or nerdctl).

    Checks ``OCI_EXE`` in *env* first, then probes ``PATH`` for known
    runtimes.  Defaults to ``'docker'`` if nothing is found.

    Parameters
    ----------
    env : dict[str, str]
        Environment variables; ``OCI_EXE`` is checked first.

    Returns
    -------
    str
        Name or path of the OCI runtime executable.
    """
    if env.get("OCI_EXE"):
        return env["OCI_EXE"]
    for cand in ("docker", "podman", "nerdctl"):
        if _which(cand):  # NOTE shutil.which ALWAYS RETURNS NONE ON WINDOWS before 3.12
            return cand
    # Default to docker name if nothing found
    return "docker"


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


def get_default_platform_build(default_python_version: str = "py311") -> str:
    """Return a default ``<platform>-<python>`` build identifier.

    Inspects the ``PIXI_ENVIRONMENT_NAME`` environment variable first;
    falls back to ``sys.platform`` detection.

    Parameters
    ----------
    default_python_version : str, optional
        Python version suffix used when not running inside pixi
        (default ``'py311'``).

    Returns
    -------
    str
        A string like ``'manylinux_2_28-py311'`` or ``'macosx-py311'``.
    """
    from_pixi = os.environ.get("PIXI_ENVIRONMENT_NAME", None)
    if from_pixi and "-" in from_pixi:
        manylinux_pixi_to_pattern_renaming: dict[str, str] = {
            "manylinux228": "manylinux_2_28",
            "manylinux234": "manylinux_2_34",
        }
        platform_prefix: str = from_pixi.split("-")[0]
        python_version: str = from_pixi.split("-")[1]
        platform_prefix = manylinux_pixi_to_pattern_renaming.get(
            platform_prefix, platform_prefix
        )
        return f"{platform_prefix}-{python_version}"
    else:
        if sys.platform == "darwin":
            return f"macosx-{default_python_version}"
        elif sys.platform.startswith("linux"):
            return f"linux-{default_python_version}"
        elif sys.platform == "win32":
            return f"windows-{default_python_version}"
    return f"unknown-{default_python_version}"
