"""Memory-aware build parallelism.

``os.cpu_count()`` alone over-subscribes template-heavy C++ on machines with
little RAM per hardware thread. Sixteen concurrent ``cl.exe`` instances on a
32 GB box is ~2 GB each, below what ITK wrapping translation units peak at,
and the result is swapping or an out-of-memory kill rather than a faster
build. Bounding jobs by physical memory keeps the machine out of that regime.

Two environment overrides exist so CI can tune without a code change:

``ITK_BUILD_JOBS``
    Total ninja jobs. Replaces the computed value entirely.
``ITK_BUILD_LOAD_LIMIT``
    Value for ninja ``-l``; defaults to the hardware thread count.

There is deliberately no separate link pool. On this build links are not
the memory pressure: link.exe peaked at 1.45 GB (one module; the median
output is 3 MB), the whole link phase is ~1.3 min of an ~80 min step, and
it overlaps the compile tail. The compilers are the constraint, and the
memory-bounded job count already limits them.
"""

from __future__ import annotations

import os
import platform
import subprocess
from collections.abc import Mapping

#: RAM to budget per concurrent compile job, calibrated by measurement on a
#: 16-thread / 31.8 GiB box (ITK 6 wrapping, MSVC 19.38, sampled every 0.5 s):
#:
#:   -j16   killed for memory pressure in 2 of 3 cold builds
#:   -j12   step 02 4842 s, peak build-process sum 15.7 GB, min free 5.75 GB
#:   -j8    step 02 5291 s, peak build-process sum 12.2 GB, min free 8.96 GB
#:
#: A single cl.exe peaks at 3.9 GB but peaks rarely coincide: the marginal
#: cost was 0.84 GB per extra job between -j8 and -j12. 2.5 GB/job lands on
#: the measured optimum (floor(31.8 / 2.5) = 12) and leaves ~5 GB of floor;
#: 2 GB/job (= cpu_count here) is the configuration that was being killed.
DEFAULT_GB_PER_JOB = 2.5


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
            raw = open(path).read().strip()
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
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return None
            return stat.ullTotalPhys / 1024**3
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
    size falls back to the CPU count, i.e. the historical behaviour.
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
    count. ninja >= 1.12 honours it on Windows too (verified on 1.13.2: eight
    3-second jobs under ``-l 0.5`` serialise to 25 s), so ``-l <jobs>`` on a
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
