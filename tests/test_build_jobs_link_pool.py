"""The Ninja link pool and the per-link LTRANS cap (issue #311)."""

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from build_jobs import (
    DEFAULT_GB_PER_LINK,
    DEFAULT_LTO_JOBS_PER_LINK,
    compute_link_jobs,
    compute_lto_jobs,
    job_pool_definitions,
    lto_jobs_definitions,
)
from cmake_argument_builder import CMakeArgumentBuilder
from linux_build_python_instance import LinuxBuildPythonInstance
from macos_build_python_instance import MacOSBuildPythonInstance
from pyproject_configure import STABLE_ABI_TAG
from target_platform import OS, Arch, TargetPlatform

MODULE_FLAGS = "CMAKE_MODULE_LINKER_FLAGS:STRING"
SHARED_FLAGS = "CMAKE_SHARED_LINKER_FLAGS:STRING"


def test_link_jobs_split_the_job_count_into_capped_links() -> None:
    """cortex: 48 jobs, 251 GB -> 12 links of 4 LTRANS processes each."""
    assert DEFAULT_LTO_JOBS_PER_LINK == 4
    assert compute_link_jobs(48, 251.3, env={}) == 12
    assert compute_lto_jobs(48, 12) == 4


def test_link_jobs_are_bounded_by_memory() -> None:
    assert DEFAULT_GB_PER_LINK == 8.0
    assert compute_link_jobs(48, 64.0, env={}) == 8
    assert compute_lto_jobs(48, 8) == 6


def test_link_jobs_never_drop_below_one() -> None:
    assert compute_link_jobs(2, 4.0, env={}) == 1
    assert compute_link_jobs(1, None, env={}) == 1
    assert compute_lto_jobs(3, 1) == 3


def test_unknown_memory_leaves_the_cpu_split() -> None:
    assert compute_link_jobs(16, None, env={}) == 4
    assert compute_link_jobs(16, 0, env={}) == 4


def test_link_jobs_override_and_zero_disables() -> None:
    assert compute_link_jobs(48, 251.3, env={"ITK_BUILD_LINK_JOBS": " 6 "}) == 6
    assert compute_link_jobs(48, 251.3, env={"ITK_BUILD_LINK_JOBS": "0"}) == 0
    assert compute_link_jobs(48, 251.3, env={"ITK_BUILD_LINK_JOBS": "-3"}) == 0


def test_job_pool_definitions() -> None:
    assert job_pool_definitions(48, 12) == {
        "CMAKE_JOB_POOLS:STRING": "compile=48;link=12",
        "CMAKE_JOB_POOL_COMPILE:STRING": "compile",
        "CMAKE_JOB_POOL_LINK:STRING": "link",
    }
    assert job_pool_definitions(48, 0) == {}


def test_lto_cap_is_appended_after_existing_linker_flags() -> None:
    """GCC honors the last -flto=, and CMake's -flto=auto precedes LINK_FLAGS."""
    defs = lto_jobs_definitions(4, {MODULE_FLAGS: "-Wl,--gc-sections"})
    assert defs == {MODULE_FLAGS: "-Wl,--gc-sections -flto=4", SHARED_FLAGS: "-flto=4"}


def test_lto_cap_leaves_a_given_flto_alone() -> None:
    defs = lto_jobs_definitions(4, {MODULE_FLAGS: "-flto=8", SHARED_FLAGS: ""})
    assert defs == {SHARED_FLAGS: "-flto=4"}


def _parallelism(builder: object, jobs: int, links: int) -> None:
    builder.build_node_cpu_count = jobs  # type: ignore[attr-defined]
    builder.build_link_jobs = links  # type: ignore[attr-defined]


def test_manylinux_caps_lto_jobs(linux_builder: LinuxBuildPythonInstance) -> None:
    _parallelism(linux_builder, 48, 12)
    defs = linux_builder.lto_link_definitions({MODULE_FLAGS: "-Wl,--gc-sections"})
    assert defs[MODULE_FLAGS] == "-Wl,--gc-sections -flto=4"


def test_no_lto_cap_without_a_link_pool(
    linux_builder: LinuxBuildPythonInstance,
) -> None:
    _parallelism(linux_builder, 48, 0)
    assert linux_builder.lto_link_definitions({}) == {}


def test_no_lto_cap_off_manylinux_or_on_macos(
    linux_builder: LinuxBuildPythonInstance,
    macos_builder: MacOSBuildPythonInstance,
) -> None:
    """GCC's -flto=<n> is an error to clang, which native Linux may use."""
    linux_builder.target = TargetPlatform(OS.LINUX, Arch.X86_64)
    for builder in (linux_builder, macos_builder):
        _parallelism(builder, 48, 12)
        assert builder.lto_link_definitions({}) == {}


def _rendered(cmd: Sequence[str | Path]) -> str:
    return " ".join(str(c) for c in cmd)


def test_job_pools_reach_the_itk_configure(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    linux_builder.cleanup = False
    linux_builder.build_node_cpu_count = 48
    linux_builder.build_load_limit = 48
    linux_builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    linux_builder.cmake_compiler_configurations.update(job_pool_definitions(48, 12))
    linux_builder.cmake_itk_source_build_configurations.set(
        "ITK_BINARY_DIR:PATH", str(tmp_path / "itk-bld")
    )
    calls: list[str] = []

    def record(cmd: Sequence[str | Path], *args: object, **kwargs: object) -> int:
        calls.append(_rendered(cmd))
        return 0

    with patch.object(linux_builder, "echo_check_call", side_effect=record):
        linux_builder.build_wrapped_itk_cplusplus()
    configure = next(c for c in calls if " -S " in c)
    assert "-DCMAKE_JOB_POOLS:STRING='compile=48;link=12'" in configure
    assert "-DCMAKE_JOB_POOL_LINK:STRING='link'" in configure


def test_job_pools_reach_a_remote_module_build(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    linux_builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    linux_builder.cmake_compiler_configurations.update(job_pool_definitions(48, 12))
    (tmp_path / "inc").mkdir()
    linux_builder.python_env = replace(
        linux_builder.python_env, include_dir=tmp_path / "inc"
    )
    module = tmp_path / "ITKFoo"
    (module / "dist").mkdir(parents=True)
    linux_builder.module_source_dir = module
    calls: list[str] = []

    def fake_build(cmd: Sequence[str | Path], *args: object, **kwargs: object) -> int:
        args_list = [str(c) for c in cmd]
        calls.append(" ".join(args_list))
        outdir = Path(args_list[args_list.index("--outdir") + 1])
        (outdir / f"itk_foo-1.0-{STABLE_ABI_TAG}-abi3-linux_x86_64.whl").write_bytes(
            b"new"
        )
        return 0

    with (
        patch.object(linux_builder, "echo_check_call", side_effect=fake_build),
        patch.object(linux_builder, "fixup_module_wheel"),
    ):
        linux_builder.build_external_module_python_wheel()
    assert (
        "--config-setting=cmake.define.CMAKE_JOB_POOLS:STRING='compile=48;link=12'"
        in calls[0]
    )
    assert (
        "--config-setting=cmake.define.CMAKE_JOB_POOL_COMPILE:STRING='compile'"
        in calls[0]
    )


def test_docker_scripts_forward_the_parallelism_overrides() -> None:
    """The overrides are read inside the container, so the scripts must pass them."""
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    forwarded = (
        "for _var in ITK_BUILD_JOBS ITK_BUILD_LOAD_LIMIT ITK_BUILD_LINK_JOBS; do"
    )
    for name in (
        "dockcross-manylinux-build-wheels.sh",
        "dockcross-manylinux-build-module-wheels.sh",
    ):
        assert forwarded in (scripts / name).read_text(), name
