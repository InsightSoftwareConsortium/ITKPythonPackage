"""Memory-aware build parallelism.

``os.cpu_count()`` alone over-subscribes template-heavy C++ on machines with
little RAM per hardware thread. Sixteen concurrent ``cl.exe`` instances on a
32 GB box is ~2 GB each, below what ITK wrapping translation units peak at,
and the result is swapping or an out-of-memory kill rather than a faster
build. Bounding jobs by physical memory keeps the machine out of that regime.

Link steps get their own Ninja job pool. ITK links each Python wrapper module
with link-time optimization, and GCC's ``-flto=auto`` starts one LTRANS
process per hardware thread in every link, so a link phase with tens of
modules ready at once runs hundreds of processes regardless of ``-j``. The
link pool bounds the concurrent links, and on manylinux each link's LTRANS
processes are capped so that the links together use about the job count.

Environment overrides, so CI can tune without a code change:

``ITK_BUILD_JOBS``
    Total ninja jobs. Replaces the computed value entirely.
``ITK_BUILD_LOAD_LIMIT``
    Value for ninja ``-l``; defaults to the hardware thread count.
``ITK_BUILD_LINK_JOBS``
    Concurrent link steps. ``0`` disables the link pool and the LTRANS cap.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

#: RAM budgeted per concurrent compile job, measured on ITK 6 wrapping with MSVC.
DEFAULT_GB_PER_JOB = 2.5
#: LTRANS processes per link, so a large module still links in parallel.
DEFAULT_LTO_JOBS_PER_LINK = 4
#: RAM budgeted per concurrent link, measured on ITK 6 wrapping with GCC LTO.
DEFAULT_GB_PER_LINK = 8.0


def _cgroup_memory_limit_gb() -> float | None:
    """Container memory limit in GiB, or ``None`` when unlimited or absent.

    ``sysconf(SC_PHYS_PAGES)`` reports the host's RAM even inside a
    memory-capped container, so a build sized from it over-commits and is
    killed. A 4 GiB container on a 24 GiB host otherwise budgets 22.5 GB.
    """
    for path, unlimited in (
        ("/sys/fs/cgroup/memory.max", "max"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes", None),
    ):
        try:
            with Path(path).open() as f:
                raw = f.read().strip()
        except OSError:
            continue
        if raw == unlimited:
            return None
        try:
            limit = int(raw)
        except ValueError:
            continue
        # cgroup v1 reports a sentinel near 2**63 when unlimited.
        if limit <= 0 or limit >= 2**62:
            return None
        return limit / 1024**3
    return None


def physical_memory_gb() -> float | None:
    """Total physical RAM in GiB, or ``None`` if it cannot be determined.

    Deliberately dependency-free (no psutil) so it runs inside the minimal
    build environments on every platform.
    """
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(  # type: ignore[attr-defined]
                ctypes.byref(stat)
            ):
                return None
            return int(stat.ullTotalPhys) / 1024**3
        if system == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            return int(out.strip()) / 1024**3
        host_gb = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3
        cgroup_gb = _cgroup_memory_limit_gb()
        return min(host_gb, cgroup_gb) if cgroup_gb else host_gb
    except Exception:
        return None


def compute_build_jobs(
    cpu_count: int | None,
    memory_gb: float | None,
    *,
    gb_per_job: float = DEFAULT_GB_PER_JOB,
    env: Mapping[str, str] | None = None,
) -> int:
    """Number of ninja jobs: the smaller of the CPU count and what RAM affords.

    ``ITK_BUILD_JOBS`` in *env* overrides the computation. An unknown memory
    size falls back to the CPU count, i.e. the historical behavior.
    """
    env = os.environ if env is None else env
    override = env.get("ITK_BUILD_JOBS", "").strip()
    if override:
        return max(1, int(override))
    cpus = max(1, int(cpu_count or 1))
    if memory_gb is None or memory_gb <= 0:
        return cpus
    # floor, not round: the budget was calibrated at the measured-safe point
    # (31.8 / 2.5 = 12.7 -> 12); rounding up would land one job past it.
    return max(1, min(cpus, int(memory_gb // gb_per_job)))


def compute_load_limit(
    cpu_count: int | None, env: Mapping[str, str] | None = None
) -> int:
    """Value for ninja ``-l``: the hardware thread count, or an override.

    ``-l`` is a *CPU* budget and must not be tied to the memory-derived job
    count. ninja >= 1.12 honors it on Windows too (verified on 1.13.2: eight
    3-second jobs under ``-l 0.5`` serialize to 25 s), so ``-l <jobs>`` on a
    box with more threads than jobs throttles ninja whenever load exceeds the
    job count -- which under a saturating compile is always. Keying it to the
    thread count makes it a no-op under normal load and a safety valve only
    when something else is loading the machine. ``ITK_BUILD_LOAD_LIMIT``
    overrides.
    """
    env = os.environ if env is None else env
    override = env.get("ITK_BUILD_LOAD_LIMIT", "").strip()
    if override:
        return max(1, int(override))
    return max(1, int(cpu_count or 1))


def compute_link_jobs(
    build_jobs: int,
    memory_gb: float | None,
    *,
    lto_jobs_per_link: int = DEFAULT_LTO_JOBS_PER_LINK,
    gb_per_link: float = DEFAULT_GB_PER_LINK,
    env: Mapping[str, str] | None = None,
) -> int:
    """Size of the Ninja ``link`` pool; ``0`` means no link pool.

    The job count divided among links of *lto_jobs_per_link* processes each,
    further bounded by what RAM affords. ``ITK_BUILD_LINK_JOBS`` in *env*
    overrides the computation.
    """
    env = os.environ if env is None else env
    override = env.get("ITK_BUILD_LINK_JOBS", "").strip()
    if override:
        return max(0, int(override))
    links = max(1, build_jobs // max(1, lto_jobs_per_link))
    if memory_gb is not None and memory_gb > 0:
        links = min(links, max(1, int(memory_gb // gb_per_link)))
    return links


def compute_lto_jobs(build_jobs: int, link_jobs: int) -> int:
    """LTRANS processes per link, so that *link_jobs* links use *build_jobs*."""
    return max(1, build_jobs // max(1, link_jobs))


def job_pool_definitions(build_jobs: int, link_jobs: int) -> dict[str, str]:
    """CMake definitions for Ninja ``compile`` and ``link`` job pools.

    Other generators ignore them. A *link_jobs* of ``0`` returns none.
    """
    if link_jobs <= 0:
        return {}
    return {
        "CMAKE_JOB_POOLS:STRING": f"compile={build_jobs};link={link_jobs}",
        "CMAKE_JOB_POOL_COMPILE:STRING": "compile",
        "CMAKE_JOB_POOL_LINK:STRING": "link",
    }


def lto_jobs_definitions(lto_jobs: int, flag_defs: Mapping[str, str]) -> dict[str, str]:
    """Append ``-flto=<lto_jobs>`` to the shared and module linker flags.

    CMake puts the IPO compile options, including GCC's ``-flto=auto``,
    before the linker flags on the link line, and GCC honors the last
    ``-flto=``. A value that already names ``-flto=`` is left as given.
    """
    out: dict[str, str] = {}
    for var in ("CMAKE_SHARED_LINKER_FLAGS", "CMAKE_MODULE_LINKER_FLAGS"):
        key = f"{var}:STRING"
        value = flag_defs.get(key, "")
        if "-flto=" not in value:
            out[key] = f"{value} -flto={lto_jobs}".strip()
    return out
