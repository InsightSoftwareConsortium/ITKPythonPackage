#!/usr/bin/env python
import argparse
import functools
import os
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from build_config import BuildConfig
from target_platform import (
    OS,
    TargetPlatform,
    manylinux_version_from_platform_env,
)
from wheel_builder_utils import (
    abort_if_wrong_pixi_environment,
    compute_itk_package_version,
    get_default_platform_build,
    is_platform_env,
    resolve_oci_exe,
    run_command,
    which_required,
    which_required_in_pixi_env,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from build_python_instance_base import BuildPythonInstanceBase


# A short root keeps Windows build paths under the 260-character limit.
WINDOWS_BUILD_DIR_ROOT = Path("C:/") / "BDR"


def remotemodulebuildandtestaction() -> dict[str, str]:
    """Collect GitHub Actions environment variables for remote module builds.

    The following environment variables are defined by the
    ``ITKRemoteModuleBuildTestPackageAction`` GitHub Action.  Variables
    marked *active* are read from the environment with a default
    fallback; those marked *not used* are documented here for
    cross-reference and are not read by this script.

    Environment Variables
    ---------------------
    ITK_PACKAGE_VERSION : str  (active)
        PEP 440 version string for ITK packages.
        GitHub Action source: ``inputs.itk-wheel-tag``.
        Default ``"auto"`` triggers automatic version computation.
    ITKPYTHONPACKAGE_TAG : str  (not used; GitHub Actions scripts only)
        Git tag for ITKPythonPackage checkout.
        GitHub Action source: ``inputs.itk-python-package-tag``.
    ITKPYTHONPACKAGE_ORG : str  (not used; GitHub Actions scripts only)
        GitHub organization owning ITKPythonPackage.
        GitHub Action source: ``inputs.itk-python-package-org``.
    ITK_MODULE_PREQ : str  (active)
        Colon-delimited list of remote module dependencies.
        GitHub Action source: ``inputs.itk-module-deps``.
    CMAKE_OPTIONS : str  (active)
        Extra options forwarded to CMake.
        GitHub Action source: ``inputs.cmake-options``.
    MANYLINUX_PLATFORM : str  (not used; computed internally)
        Full manylinux platform string (e.g. ``"manylinux_2_28-x64"``).
        GitHub Action source: ``matrix.manylinux-platform``.
    MANYLINUX_VERSION : str  (active)
        Manylinux specification (e.g. ``"_2_28"``).
    TARGET_ARCH : str  (not used; computed internally)
        Target architecture (e.g. ``"x64"``).
    MACOSX_DEPLOYMENT_TARGET : str  (active)
        Minimum macOS version for wheel compatibility.
        GitHub Action source: ``inputs.macosx-deployment-target``.
        Default ``"14.0"`` matches the arm64-only macOS wheel target.

    Returns
    -------
    dict[str, str]
        A mapping of active configuration keys to their values, sourced
        from environment variables with sensible defaults.
    """
    env_defaults: dict[str, str] = {
        "ITK_PACKAGE_VERSION": "gitauto",
        "ITK_MODULE_PREQ": "",
        "CMAKE_OPTIONS": "",
        "MANYLINUX_VERSION": "",
        "MACOSX_DEPLOYMENT_TARGET": "14.0",
    }
    return {key: os.environ.get(key, default) for key, default in env_defaults.items()}


def itk_git_env(itk_source_dir: Path) -> dict[str, str]:
    """Return an environment in which git cannot see a repository enclosing the ITK tree."""
    env = os.environ.copy()
    env["GIT_CEILING_DIRECTORIES"] = str(Path(itk_source_dir).resolve().parent)
    return env


def sync_itk_source(itk_source_dir: Path, itk_git_tag: str) -> str:
    """Bring the ITK source tree to *itk_git_tag* and return the revision in use."""
    git_env = itk_git_env(itk_source_dir)
    # A cache-restored tree keeps an empty .git, so ask git; its sources already match the binaries.
    itk_source_is_repository = (
        run_command(
            ["git", "rev-parse", "--git-dir"],
            cwd=itk_source_dir,
            env=git_env,
        ).returncode
        == 0
    )
    if not itk_source_is_repository:
        print(
            f"WARNING: {itk_source_dir} is not a git repository; using "
            f"its sources as they are and not checking out "
            f"{itk_git_tag!r}."
        )
    else:
        fetch_result = run_command(
            ["git", "fetch", "--tags", "origin"],
            cwd=itk_source_dir,
            env=git_env,
        )
        if fetch_result.returncode != 0:
            # Only fatal when the requested revision is not already present.
            have_revision = run_command(
                [
                    "git",
                    "rev-parse",
                    "--verify",
                    "--quiet",
                    f"{itk_git_tag}^{{commit}}",
                ],
                cwd=itk_source_dir,
                env=git_env,
            )
            if have_revision.returncode != 0:
                msg = (
                    f"Failed to fetch ITK tags in {itk_source_dir}: "
                    f"{fetch_result.stderr}"
                )
                raise RuntimeError(msg)
            print(
                f"WARNING: Failed to fetch ITK tags in {itk_source_dir}; "
                f"using the local {itk_git_tag!r}: {fetch_result.stderr}"
            )
        checkout_result = run_command(
            ["git", "checkout", itk_git_tag],
            cwd=itk_source_dir,
            env=git_env,
        )
        if checkout_result.returncode != 0:
            # Keep the checked-out commit: a cache-restored tree must match its binaries.
            head_result = run_command(
                ["git", "rev-parse", "HEAD"],
                cwd=itk_source_dir,
                env=git_env,
            )
            resolved = head_result.stdout.strip() if head_result.returncode == 0 else ""
            print(
                f"WARNING: Failed to checkout {itk_git_tag}; keeping the "
                f"commit already checked out ({resolved or 'unknown'}): "
                f"{checkout_result.stderr}"
            )
            if resolved:
                itk_git_tag = resolved
    return itk_git_tag


def module_dependencies_root(
    build_dir_root: str | Path, supplied: str | Path | None
) -> Path:
    """Return where module dependencies are cloned, defaulting under the build root."""
    if not supplied:
        return Path(build_dir_root) / "MODULE_DEPENDENCIES"
    return Path(supplied)


def derives_package_version(itk_package_version: str | None) -> bool:
    """Return True when *itk_package_version* asks for a version derived from git."""
    return itk_package_version in (None, "", "gitauto", "auto")


def source_date_epoch(env: "Mapping[str, str]", commit_time: str | None) -> str | None:
    """Return the wheels' zip timestamp: the caller's SOURCE_DATE_EPOCH, else the ITK commit's time."""
    if env.get("SOURCE_DATE_EPOCH"):
        return env["SOURCE_DATE_EPOCH"]
    commit_time = (commit_time or "").strip()
    return commit_time if commit_time.isdigit() else None


def windows_link_options(os_name: OS, link_options: str | None) -> str | None:
    """Return *link_options* (the _LINK_ value) with /Brepro added on Windows."""
    if os_name is not OS.WINDOWS:
        return link_options
    link_options = link_options or ""
    if any(o.lower() in ("/brepro", "-brepro") for o in link_options.split()):
        return link_options
    return f"{link_options} /Brepro".lstrip()


def itk_commit_time(itk_source_dir: Path, itk_git_tag: str) -> str | None:
    """Return the committer time of *itk_git_tag*, or None without a repository."""
    result = run_command(
        ["git", "log", "-1", "--format=%ct", itk_git_tag],
        cwd=itk_source_dir,
        env=itk_git_env(itk_source_dir),
    )
    return result.stdout if result.returncode == 0 else None


def in_manylinux_container(env: "Mapping[str, str]") -> bool:
    """True inside a dockcross image (CROSS_TRIPLE) or a pypa one (AUDITWHEEL_PLAT)."""
    return bool(env.get("CROSS_TRIPLE") or env.get("AUDITWHEEL_PLAT"))


def in_pixi_env() -> bool:
    """Check whether the process is running inside a pixi environment.

    Returns
    -------
    bool
        True if both ``PIXI_ENVIRONMENT_NAME`` and ``PIXI_PROJECT_ROOT``
        are set in the environment.
    """
    return "PIXI_ENVIRONMENT_NAME" in os.environ and "PIXI_PROJECT_ROOT" in os.environ


def get_effective_command_line(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> str:
    """Reconstruct a reproducible command line from parsed arguments.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The argument parser used to parse *args*.
    args : argparse.Namespace
        Parsed command-line arguments.

    Returns
    -------
    str
        A shell-safe command string suitable for logging or re-execution
        inside a pixi environment.
    """
    pixi_executable: str = os.environ.get("PIXI_EXE", "pixi")
    effective_command = [
        pixi_executable,
        "run",
        "-e",
        args.platform_env,
        "--",
        sys.executable,
        sys.argv[0],
    ]
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        dest = action.dest
        value = getattr(args, dest, None)
        if value is None:
            continue
        if action.option_strings:
            option_string = action.option_strings[0]
            if isinstance(action, argparse._StoreTrueAction):
                if value:
                    effective_command.append(option_string)
            elif isinstance(action, argparse._StoreFalseAction):
                if not value:
                    effective_command.append(option_string)
            elif isinstance(value, list):
                if value:
                    effective_command.append(option_string)
                    effective_command.extend([str(v) for v in value])
            else:
                effective_command.append(option_string)
                effective_command.append(str(value))
        elif isinstance(value, list):
            effective_command.extend([str(v) for v in value])
        else:
            effective_command.append(str(value))
    return shlex.join(effective_command)


def parse_args_with_cmake_defines(
    parser: argparse.ArgumentParser, argv: list[str] | None = None
) -> argparse.Namespace:
    """Parse *argv*, appending every ``-D`` CMake definition to ``cmake_options``.

    argparse reads a ``-`` token without spaces as an unknown option, so
    ``-D`` definitions are taken out first and appended in command-line order.
    """
    argv = sys.argv[1:] if argv is None else list(argv)
    defines = [a for a in argv if a.startswith("-D")]
    args = parser.parse_args([a for a in argv if not a.startswith("-D")])
    args.cmake_options = [*args.cmake_options, *defines]
    return args


def default_build_dir_root(ipp_dir: Path, os_name: OS) -> Path:
    """The build root used when --build-dir-root is not given."""
    # Windows gets a very short path to avoid path-too-long errors.
    if os_name is OS.WINDOWS:
        return WINDOWS_BUILD_DIR_ROOT
    return ipp_dir.parent / "ITKPythonPackage-build"


def split_cmake_options(text: str, os_name: OS) -> list[str]:
    """Split ``CMAKE_OPTIONS`` as a shell would, keeping Windows paths' backslashes."""
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    if os_name is OS.WINDOWS:
        lexer.escape = ""
    return list(lexer)


def build_argument_parser(os_name: OS, ipp_dir: Path) -> argparse.ArgumentParser:
    """Return the command line parser; defaults come from the environment."""
    remote_module_build_dict = remotemodulebuildandtestaction()
    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
    )
    # The environment guard requires the active pixi environment itself, which
    # get_default_platform_build renames for manylinux.
    default_env = os.environ.get("PIXI_ENVIRONMENT_NAME", "")
    if not is_platform_env(default_env):
        default_env = get_default_platform_build("py311")
    parser.add_argument(
        "--platform-env",
        default=default_env,
        help=(
            """A platform environment name or path:
               linux-py311,
               manylinux228-py311,
               windows-py311,
               macosx-py311
            """
        ),
    )
    parser.add_argument(
        "--cleanup",
        dest="cleanup",
        action="store_true",
        help="""
        Remove temporary build files (intermediate objects, generated
        sources, CastXML output) once the build completes. Omitted, the
        files are kept. Ignored when --build-itk-tarball-cache is given,
        because the cache step needs those files.
        """,
    )
    parser.add_argument(
        "--lib-paths",
        action="append",
        default=[],
        help=(
            "Windows only: semicolon-delimited library directories for delvewheel "
            "to include in module wheel; may be repeated"
        ),
    )
    parser.add_argument(
        "--exclude-libs",
        action="append",
        default=[],
        help=(
            "Windows and Linux: semicolon-delimited library names delvewheel or "
            'auditwheel must not bundle, e.g. "nvcuda.dll" or "libcuda.so.1"; '
            "may be repeated"
        ),
    )
    parser.add_argument(
        "cmake_options",
        nargs="*",
        default=split_cmake_options(remote_module_build_dict["CMAKE_OPTIONS"], os_name),
        help="Extra options to pass to CMake, e.g. -DBUILD_SHARED_LIBS:BOOL=OFF.\n"
        "   These will override defaults if duplicated",
    )
    parser.add_argument(
        "--module-source-dir",
        type=str,
        default=None,
        help="Path to the (remote) module source directory to build.",
    )
    parser.add_argument(
        "--module-dependencies-root-dir",
        type=str,
        default=None,
        help="Path to the root directory for module dependencies.\n"
        "This is the path where a remote module dependencies (other remote modules)\n"
        "are searched for, or automatically git cloned to.",
    )
    parser.add_argument(
        "--itk-module-deps",
        type=str,
        default=remote_module_build_dict["ITK_MODULE_PREQ"],
        help="Colon-delimited list of a remote modules dependencies.\n"
        "'gitorg/repo@tag:gitorg/repo@tag:gitorg/repo@tag'\n"
        "These are set in ITKRemoteModuleBuildTestPackageAction:itk-module-deps github actions.\n"
        "The default comes from the ITK_MODULE_PREQ environment variable.",
    )

    parser.add_argument(
        "--build-itk-tarball-cache",
        dest="build_itk_tarball_cache",
        action="store_true",
        default=False,
        help="Build an uploadable tarball.  The tarball can be used as a cache for remote module builds.",
    )
    parser.add_argument(
        "--no-build-itk-tarball-cache",
        dest="build_itk_tarball_cache",
        action="store_false",
        help="Do not build an uploadable tarball.  The tarball can be used as a cache for remote module builds.",
    )

    build_dir_root = default_build_dir_root(ipp_dir, os_name)
    parser.add_argument(
        "--build-dir-root",
        type=str,
        default=f"{build_dir_root}",
        help="The root of the build resources.",
    )
    parser.add_argument(
        "--manylinux-version",
        type=str,
        default=remote_module_build_dict["MANYLINUX_VERSION"],
        help="default manylinux version (_2_28, _2_34, ...), if empty, build native linux instead of cross compiling",
    )

    parser.add_argument(
        "--itk-git-tag",
        type=str,
        default=os.environ.get(
            "ITK_GIT_TAG", os.environ.get("ITK_PACKAGE_VERSION", "main")
        ),
        help="""
        - 'ITK_GIT_TAG': Tag/branch/hash for the ITK source code to use in packaging.
           Which ITK git tag/hash/branch to use as reference for building wheels/modules
           https://github.com/InsightSoftwareConsortium/ITK.git@${ITK_GIT_TAG}
           Examples: v5.4.0, v5.2.1.post1, 0ffcaed12552, my-testing-branch
           See available release tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags
        """,
    )

    parser.add_argument(
        "--itk-source-dir",
        type=str,
        default=os.environ.get("ITK_SOURCE_DIR", str(build_dir_root / "ITK")),
        help="""
        - 'ITK_SOURCE_DIR':  When building different 'flavor' of ITK python packages
          on a given platform, explicitly setting the ITK_SOURCE_DIR options allow to
          speed up source-code downloads by reusing an existing repository.
          If the requested directory does not exist, manually clone and checkout ${ITK_GIT_TAG}""",
    )

    parser.add_argument(
        "--itk-package-version",
        type=str,
        default=remote_module_build_dict["ITK_PACKAGE_VERSION"],
        help="""
        - 'ITK_PACKAGE_VERSION' A valid PEP440 version string for the itk packages
          generated, or 'gitauto' to derive one from the ITK source repository with
          git describe.
          Any other value is used as given, which is what a source tree restored from
          a build cache needs: such a tree carries no repository, so 'gitauto' cannot
          work there.
          (in github action ITKRemoteModuleBuildTestPackage itk-wheel-tag sets this)
       """,
    )

    if os_name is OS.DARWIN:
        parser.add_argument(
            "--macosx-deployment-target",
            type=str,
            default=remote_module_build_dict["MACOSX_DEPLOYMENT_TARGET"],
            help="""
            The MacOSX deployment target to use for building wheels.
             """,
        )

    parser.add_argument(
        "--use-compiler-cache",
        "--use-ccache",
        action="store_true",
        dest="use_ccache",
        default=None,
        help="""
         -  Compile through sccache on Windows or ccache elsewhere. Without this
            flag or its --no- form, USE_COMPILER_CACHE or USE_CCACHE decides.
         """,
    )
    parser.add_argument(
        "--no-use-compiler-cache",
        "--no-use-ccache",
        action="store_false",
        dest="use_ccache",
        help="""
         -  Do not use a compiler cache, whatever the environment says
         """,
    )

    parser.add_argument(
        "--dead-strip",
        action="store_true",
        dest="dead_strip",
        default=True,
        help="""
         -  Linux and macOS, on by default: drop unreferenced code and export
            only PyInit_* from Python modules
         """,
    )
    parser.add_argument(
        "--no-dead-strip",
        action="store_false",
        dest="dead_strip",
        help="""
         -  Link without dead stripping
         """,
    )

    parser.add_argument(
        "--skip-itk-build",
        action="store_true",
        dest="skip_itk_build",
        default=False,
        help="""
         -  Option to skip the ITK C++ build step (Step 2)
         """,
    )

    parser.add_argument(
        "--no-skip-itk-build",
        action="store_false",
        dest="skip_itk_build",
        help="""
         -  Option to not skip the ITK C++ build step (Step 2)
         """,
    )

    parser.add_argument(
        "--skip-itk-wheel-build",
        action="store_true",
        dest="skip_itk_wheel_build",
        default=False,
        help="""
         -  Option to skip the ITK wheel build step (Step 3)
         """,
    )

    parser.add_argument(
        "--no-skip-itk-wheel-build",
        action="store_false",
        dest="skip_itk_wheel_build",
        help="""
         -  Option to not skip the ITK wheel build step (Step 3)
         """,
    )

    parser.add_argument(
        "--module-itk-dir",
        dest="module_itk_dir",
        choices=("build", "install"),
        default="build",
        help="""
         -  Which ITK tree a remote module (Step 6) is configured against.
            'build' (default) passes the ITK build tree as ITK_DIR.
            'install' first runs 'cmake --install' on that build tree and
            passes <prefix>/lib/cmake/ITK-<version> instead; it needs an ITK
            that installs its module build files and wrapping infrastructure
            (ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES).
         """,
    )
    return parser


def parse_arguments(
    parser: argparse.ArgumentParser, ipp_dir: Path, os_name: OS
) -> argparse.Namespace:
    """Parse the command line and settle the build and ITK source paths."""
    args = parse_args_with_cmake_defines(parser)

    abort_if_wrong_pixi_environment(args.platform_env)

    # Never None, so a build naming module dependencies always has a clone root.
    args.module_dependencies_root_dir = module_dependencies_root(
        args.build_dir_root, args.module_dependencies_root_dir
    )

    build_dir_root = default_build_dir_root(ipp_dir, os_name)
    args.build_dir_root = Path(args.build_dir_root)
    if str(args.build_dir_root) != str(build_dir_root) and str(
        args.itk_source_dir
    ) == str(build_dir_root / "ITK"):
        args.itk_source_dir = args.build_dir_root / "ITK"
    args.itk_source_dir = Path(args.itk_source_dir)
    return args


def resolve_environment(args: argparse.Namespace, ipp_dir: Path, os_name: OS) -> Path:
    """Put the pixi environment's tools first on PATH and return pixi."""
    env_bin_dir: str = "Scripts" if os_name is OS.WINDOWS else "bin"

    env_path = ipp_dir / ".pixi" / "envs" / args.platform_env
    env_subdirs = (
        [env_bin_dir, "Library/bin"] if os_name is OS.WINDOWS else [env_bin_dir]
    )

    os.environ["PATH"] = os.pathsep.join(
        [
            *[str(env_path / d) for d in env_subdirs],
            str(ipp_dir / ".pixi" / "bin"),
            os.environ.get("PATH", ""),
        ]
    )
    return which_required("pixi")


def sync_itk_source_tree(args: argparse.Namespace, ipp_dir: Path) -> None:
    """Clone ITK when absent, check out the tag, and settle the package version."""
    if not Path(args.itk_source_dir).exists():
        args.itk_source_dir.parent.mkdir(parents=True, exist_ok=True)
        print(f"Cloning ITK into {args.itk_source_dir}...")
        run_result = run_command(
            [
                "git",
                "clone",
                "https://github.com/InsightSoftwareConsortium/ITK.git",
                str(args.itk_source_dir),
            ],
            cwd=ipp_dir,
            env=os.environ.copy(),
        )
        if run_result.returncode != 0:
            msg = f"Failed to clone ITK: {run_result.stderr}"
            raise RuntimeError(msg)

    args.itk_git_tag = sync_itk_source(args.itk_source_dir, args.itk_git_tag)

    # 'gitauto' (or its alias 'auto') derives the version from the ITK repository;
    # any other value is used as given, as a cache-restored tree has no repository.
    if derives_package_version(args.itk_package_version):
        args.itk_package_version = compute_itk_package_version(
            args.itk_source_dir, args.itk_git_tag, itk_git_env(args.itk_source_dir)
        )


def pin_build_timestamps(args: argparse.Namespace, os_name: OS) -> None:
    """Make the wheels' zip entries and Windows PE headers reproducible."""
    # Every wheel writer and repair tool stamps zip entries with this time.
    epoch = source_date_epoch(
        os.environ, itk_commit_time(args.itk_source_dir, args.itk_git_tag)
    )
    if epoch:
        os.environ["SOURCE_DATE_EPOCH"] = epoch
    else:
        print(
            "WARNING: No ITK commit time and no SOURCE_DATE_EPOCH; "
            "wheel zip timestamps will be the build time."
        )

    # link.exe appends _LINK_ to every command line; /Brepro replaces PE link timestamps.
    link_options = windows_link_options(os_name, os.environ.get("_LINK_"))
    if link_options:
        os.environ["_LINK_"] = link_options


def assemble_build_config(
    args: argparse.Namespace,
    os_name: OS,
    target: TargetPlatform,
    pixi_executable: Path,
) -> BuildConfig:
    """Resolve the build tools and the target, then validate the configuration."""
    # Build tools come from the target environment, not the launching one, so a
    # stray same-named executable on PATH cannot be handed to CMake.
    cmake, ninja, doxygen, git = (
        which_required_in_pixi_env(tool_name, pixi_executable, args.platform_env)
        for tool_name in ("cmake", "ninja", "doxygen", "git")
    )

    if os.environ.get("PIXI_ENVIRONMENT_NAME") == args.platform_env:
        # A nested pixi run would overflow the cmd.exe line limit on Windows.
        python_executable = sys.executable
    else:
        cmd = [
            pixi_executable,
            "run",
            "-e",
            args.platform_env,
            "python",
            "-c",
            "import sys; print(sys.executable)",
        ]
        python_probe = run_command(cmd, env=os.environ.copy())
        if python_probe.returncode != 0 or not python_probe.stdout.strip():
            msg = (
                f"Could not resolve the python interpreter for pixi environment "
                f"{args.platform_env!r}: {python_probe.stderr}"
            )
            raise RuntimeError(msg)
        python_executable = python_probe.stdout.strip()

    oci_exe = resolve_oci_exe(os.environ.copy())

    if os_name is OS.LINUX:
        target = configure_linux_target(args)
    return BuildConfig.from_args_and_env(
        args,
        os.environ,
        target=target,
        pixi_executable=pixi_executable,
        cmake_executable=cmake,
        ninja_executable=ninja,
        doxygen_executable=doxygen,
        git_executable=git,
        python_executable=python_executable,
        oci_exe=oci_exe,
    )


def configure_linux_target(args: argparse.Namespace) -> TargetPlatform:
    """Resolve the Linux target, refusing a manylinux one outside its container."""
    # A manylinux environment always means manylinux wheels.
    if not args.manylinux_version:
        args.manylinux_version = manylinux_version_from_platform_env(args.platform_env)
    # Manylinux/docker bits for Linux. The command line wins over the
    # environment, so pin it before the target is resolved.
    if args.manylinux_version:
        os.environ["MANYLINUX_VERSION"] = args.manylinux_version
    target = TargetPlatform.detect(os.environ)
    if args.manylinux_version and not in_manylinux_container(os.environ):
        msg = (
            f"ERROR: MANYLINUX_VERSION={args.manylinux_version} "
            f"and TARGET_ARCH={target.arch.value} but not "
            f"building in dockcross.\n"
            f"  manylinux wheels are built inside the container; "
            f"start it with:\n"
            f"      ITK_SOURCE_DIR={args.itk_source_dir} "
            f"ITK_GIT_TAG={args.itk_git_tag} "
            f"ITK_PACKAGE_VERSION={args.itk_package_version} \\\n"
            f"        bash scripts/dockcross-manylinux-build-wheels.sh\n"
            f"  For wheels tied to this host instead, use "
            f"--platform-env linux-py311."
        )
        raise RuntimeError(msg)
    return target


def semicolon_joined(values: list[str]) -> list[str]:
    """Join a repeated option into the one-element list the builders take."""
    return [";".join(values)] if values else []


def make_builder(
    args: argparse.Namespace,
    os_name: OS,
    config: BuildConfig,
) -> "BuildPythonInstanceBase":
    """Construct the platform's builder."""
    # Platform-only options go to the one builder that takes them.
    builder_cls: Callable[..., BuildPythonInstanceBase]
    if os_name is OS.WINDOWS:
        from windows_build_python_instance import WindowsBuildPythonInstance

        builder_cls = functools.partial(
            WindowsBuildPythonInstance,
            windows_extra_lib_paths=semicolon_joined(args.lib_paths),
            windows_exclude_libs=semicolon_joined(args.exclude_libs),
        )
    elif os_name is OS.DARWIN:
        from macos_build_python_instance import MacOSBuildPythonInstance

        builder_cls = MacOSBuildPythonInstance
    else:
        from linux_build_python_instance import LinuxBuildPythonInstance

        builder_cls = functools.partial(
            LinuxBuildPythonInstance, exclude_libs=semicolon_joined(args.exclude_libs)
        )
    return builder_cls(
        platform_env=args.platform_env,
        build_dir_root=args.build_dir_root,
        config=config,
        cleanup=args.cleanup,
        build_itk_tarball_cache=args.build_itk_tarball_cache,
        cmake_options=args.cmake_options,
        dist_dir=args.build_dir_root / "dist",
        module_source_dir=args.module_source_dir,
        module_dependencies_root_dir=args.module_dependencies_root_dir,
        itk_module_deps=args.itk_module_deps,
        skip_itk_build=args.skip_itk_build,
        skip_itk_wheel_build=args.skip_itk_wheel_build,
        module_itk_dir=args.module_itk_dir,
    )


def write_effective_command_line(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    """Print the effective command line and save it beside the build."""
    print("=" * 80)
    print("=" * 80)
    print("= Building Wheels with effective command line")
    print("\n\n")
    cmdline: str = f"{get_effective_command_line(parser, args)}"
    args.build_dir_root.mkdir(parents=True, exist_ok=True)
    with (args.build_dir_root / f"effective_cmdline_{args.platform_env}.sh").open(
        "w"
    ) as f:
        f.write("#!/bin/bash\n")
        f.write(
            "# Generated by build_wheels.py as documentation for describing how these wheels were created.\n"
        )
        f.write(cmdline)
        f.write("\n")
    print(f"cmdline: {cmdline}")
    print("\n\n\n\n")
    print("=" * 80)
    print("=" * 80)
    print(f"Building wheels for platform: {args.platform_env}")


def build_wheels_main() -> None:
    """Entry point: parse arguments, configure, and run the wheel build."""
    # Pre-parse: the command line has not been read yet, so ambient
    # MANYLINUX_VERSION must not influence this resolution.
    target = TargetPlatform.detect(os.environ, manylinux_version="")
    os_name = target.os_name
    ipp_dir: Path = Path(__file__).parent.parent
    if (ipp_dir / ".pixi" / "bin").exists():
        os.environ["PATH"] = (
            str(ipp_dir / ".pixi" / "bin") + os.pathsep + os.environ["PATH"]
        )

    parser = build_argument_parser(os_name, ipp_dir)
    args = parse_arguments(parser, ipp_dir, os_name)
    pixi_executable = resolve_environment(args, ipp_dir, os_name)
    sync_itk_source_tree(args, ipp_dir)
    pin_build_timestamps(args, os_name)
    config = assemble_build_config(args, os_name, target, pixi_executable)
    write_effective_command_line(parser, args)
    builder = make_builder(args, os_name, config)
    builder.run()


if __name__ == "__main__":
    build_wheels_main()
