import build_jobs
import pytest
from build_jobs import (
    DEFAULT_GB_PER_JOB,
    compute_build_jobs,
    compute_load_limit,
    physical_memory_gb,
)


def test_jobs_are_bounded_by_memory_not_just_cpus():
    """16 threads on 32 GB must not yield -j16: that is 2 GB/job and thrashes."""
    assert compute_build_jobs(16, 32.0, env={}) == 12


def test_jobs_are_bounded_by_cpus_when_memory_is_plentiful():
    assert compute_build_jobs(8, 256.0, env={}) == 8


def test_unknown_memory_falls_back_to_cpu_count():
    """Historical behaviour when RAM cannot be determined."""
    assert compute_build_jobs(12, None, env={}) == 12
    assert compute_build_jobs(12, 0, env={}) == 12


def test_jobs_never_drop_below_one():
    assert compute_build_jobs(16, 1.0, env={}) == 1
    assert compute_build_jobs(None, None, env={}) == 1


def test_env_override_replaces_the_computation():
    assert compute_build_jobs(16, 32.0, env={"ITK_BUILD_JOBS": "3"}) == 3
    assert compute_build_jobs(16, 32.0, env={"ITK_BUILD_JOBS": " 5 "}) == 5


def test_env_override_is_clamped_to_one():
    assert compute_build_jobs(16, 32.0, env={"ITK_BUILD_JOBS": "0"}) == 1


def test_gb_per_job_is_the_documented_default():
    assert DEFAULT_GB_PER_JOB == 2.5
    assert compute_build_jobs(64, 40.0, env={}) == 16


def test_physical_memory_is_plausible_on_the_host():
    """Runs for real on every platform the suite runs on."""
    gb = physical_memory_gb()
    assert gb is None or 0.5 < gb < 65536


def test_load_limit_is_the_thread_count_not_the_job_count():
    """-l is a CPU budget. Tying it to the memory-derived -j throttled a
    16-thread box to one compiler at a time (ninja honours -l on Windows)."""
    assert compute_load_limit(16, env={}) == 16
    assert compute_load_limit(16, env={}) != compute_build_jobs(16, 32.0, env={})


def test_load_limit_override_and_floor():
    assert compute_load_limit(16, env={"ITK_BUILD_LOAD_LIMIT": "12"}) == 12
    assert compute_load_limit(16, env={"ITK_BUILD_LOAD_LIMIT": "0"}) == 1
    assert compute_load_limit(None, env={}) == 1


def test_budget_reproduces_the_measured_optimum():
    """The calibration point: 16 threads, 31.8 GiB -> -j12.

    Measured 2026-09-19: -j12 finished with 5.75 GB free at peak and was
    within 3% of -j16's step-02 time, while -j16 was killed for memory
    pressure in 2 of 3 cold builds. The budget must land on 12, not 13.
    """
    assert compute_build_jobs(16, 31.8, env={}) == 12


def test_budget_floors_rather_than_rounds_up():
    """32.4 GiB / 2.5 = 12.96: rounding would give 13, one past the tested point."""
    assert compute_build_jobs(16, 32.4, env={}) == 12


def test_the_killed_configuration_is_not_reproduced():
    """2 GB/job is cpu_count on this box, i.e. the setting that was being killed."""
    assert compute_build_jobs(16, 31.8, gb_per_job=2.0, env={}) == 15
    assert compute_build_jobs(16, 31.8, env={}) < 15


def _fake_open(mapping):
    real_open = open

    def fake(path, *args, **kwargs):
        key = str(path)
        if key in mapping:
            import io

            return io.StringIO(mapping[key])
        if key.startswith("/sys/fs/cgroup/"):
            raise OSError("no such cgroup file")
        return real_open(path, *args, **kwargs)

    return fake


def _linux_host_with(monkeypatch, host_gb, cgroup_files):
    monkeypatch.setattr(build_jobs.platform, "system", lambda: "Linux")
    # os.sysconf does not exist on Windows; the Linux branch under test never
    # runs there, but the stub must still be installable so the test can run.
    monkeypatch.setattr(
        build_jobs.os,
        "sysconf",
        lambda name: int(host_gb * 1024**3) // 4096 if "PHYS" in str(name) else 4096,
        raising=False,
    )
    monkeypatch.setattr("builtins.open", _fake_open(cgroup_files))


def test_cgroup_v2_limit_caps_reported_memory(monkeypatch):
    """A capped container must not size the build from the host's RAM."""
    _linux_host_with(monkeypatch, 24.0, {"/sys/fs/cgroup/memory.max": str(4 * 1024**3)})
    assert build_jobs.physical_memory_gb() == pytest.approx(4.0)


def test_cgroup_unlimited_falls_back_to_host(monkeypatch):
    _linux_host_with(monkeypatch, 24.0, {"/sys/fs/cgroup/memory.max": "max"})
    assert build_jobs.physical_memory_gb() == pytest.approx(24.0)


def test_cgroup_v1_sentinel_treated_as_unlimited(monkeypatch):
    _linux_host_with(
        monkeypatch,
        24.0,
        {"/sys/fs/cgroup/memory/memory.limit_in_bytes": str(2**63 - 1)},
    )
    assert build_jobs.physical_memory_gb() == pytest.approx(24.0)


def test_no_cgroup_files_uses_host_memory(monkeypatch):
    _linux_host_with(monkeypatch, 24.0, {})
    assert build_jobs.physical_memory_gb() == pytest.approx(24.0)
