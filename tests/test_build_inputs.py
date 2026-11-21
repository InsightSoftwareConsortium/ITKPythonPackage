"""A run re-runs its steps when the ITK commit, version, or fingerprint changes."""

import subprocess
from collections import OrderedDict
from pathlib import Path

import pytest
from build_inputs import build_fingerprint, module_source_state, resolved_itk_commit
from cmake_argument_builder import CMakeArgumentBuilder


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def itk_source(tmp_path):
    src = tmp_path / "ITK"
    src.mkdir()
    _git(src, "init", "--quiet", "--initial-branch=main")
    _git(src, "config", "user.email", "test@example.com")
    _git(src, "config", "user.name", "Test")
    _git(src, "commit", "--quiet", "--allow-empty", "-m", "first")
    return src


@pytest.fixture
def ipp_dir(tmp_path):
    ipp = tmp_path / "IPP"
    (ipp / "scripts").mkdir(parents=True)
    (ipp / "scripts" / "build_wheels.py").write_text("print('build')\n")
    (ipp / "cmake").mkdir()
    (ipp / "cmake" / "Utils.cmake").write_text("set(X 1)\n")
    (ipp / "pixi.lock").write_text("lock 1\n")
    return ipp


def _commit(src: Path) -> str:
    _git(src, "commit", "--quiet", "--allow-empty", "-m", "next")
    return _git(src, "rev-parse", "HEAD")


def test_a_branch_name_resolves_to_the_commit_it_builds(itk_source):
    before = resolved_itk_commit(itk_source, "main")
    after = _commit(itk_source)
    assert resolved_itk_commit(itk_source, "main") == after != before


def test_a_tree_without_a_repository_reports_the_requested_revision(tmp_path):
    """A cache-restored tree inside some other repository must not borrow it."""
    _git(tmp_path, "init", "--quiet")
    src = tmp_path / "restored" / "ITK"
    src.mkdir(parents=True)
    assert resolved_itk_commit(src, "v6.0b03") == "v6.0b03"


@pytest.mark.parametrize(
    "edit",
    [
        lambda ipp: (ipp / "scripts" / "build_wheels.py").write_text("print(2)\n"),
        lambda ipp: (ipp / "cmake" / "Utils.cmake").write_text("set(X 2)\n"),
        lambda ipp: (ipp / "pixi.lock").write_text("lock 2\n"),
        lambda ipp: (ipp / "scripts" / "new_helper.py").write_text(""),
    ],
)
def test_editing_a_build_file_changes_the_fingerprint(ipp_dir, edit):
    before = build_fingerprint(ipp_dir, {})
    edit(ipp_dir)
    assert build_fingerprint(ipp_dir, {}) != before


def test_a_changed_setting_changes_the_fingerprint(ipp_dir):
    settings = {"cmdline:CMAKE_CXX_FLAGS:STRING": "-O2"}
    before = build_fingerprint(ipp_dir, settings)
    assert build_fingerprint(ipp_dir, dict(settings)) == before
    changed = {"cmdline:CMAKE_CXX_FLAGS:STRING": "-O3"}
    assert build_fingerprint(ipp_dir, changed) != before


def test_compiled_python_does_not_change_the_fingerprint(ipp_dir):
    before = build_fingerprint(ipp_dir, {})
    cache = ipp_dir / "scripts" / "__pycache__"
    cache.mkdir()
    (cache / "build_wheels.cpython-311.pyc").write_bytes(b"\0")
    assert build_fingerprint(ipp_dir, {}) == before


def _wire_run(
    builder,
    tmp_path: Path,
    ipp_dir: Path,
    itk_source: Path,
    version: str = "6.0b3",
    module: Path | None = None,
) -> list[str]:
    """Make builder.run() execute recorded no-op steps and nothing else."""
    builder.ipp_dir = ipp_dir
    builder.module_source_dir = module
    builder.dist_dir = tmp_path / "dist"
    builder.itk_module_deps = None
    builder.compiler_cache_commands = ([], [])
    builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    builder.package_env_config.update(
        {
            "ITK_SOURCE_DIR": itk_source,
            "ITK_GIT_TAG": "main",
            "ITK_PACKAGE_VERSION": version,
        }
    )
    ran: list[str] = []
    builder.build_step_table = lambda: OrderedDict(
        (name, lambda name=name: ran.append(name))
        for name in ("01_superbuild", "02_build_itk", "03_build_wheels")
    )
    return ran


def test_a_rerun_with_identical_inputs_skips_the_finished_steps(
    linux_builder, tmp_path, ipp_dir, itk_source
):
    _wire_run(linux_builder, tmp_path, ipp_dir, itk_source)
    linux_builder.run()
    ran = _wire_run(linux_builder, tmp_path, ipp_dir, itk_source)
    linux_builder.run()
    assert ran == []


def test_a_new_itk_commit_runs_every_step_again(
    linux_builder, tmp_path, ipp_dir, itk_source
):
    _wire_run(linux_builder, tmp_path, ipp_dir, itk_source)
    linux_builder.run()
    _commit(itk_source)
    ran = _wire_run(linux_builder, tmp_path, ipp_dir, itk_source)
    linux_builder.run()
    assert ran == ["01_superbuild", "02_build_itk", "03_build_wheels"]


def test_a_new_package_version_runs_every_step_again(
    linux_builder, tmp_path, ipp_dir, itk_source
):
    _wire_run(linux_builder, tmp_path, ipp_dir, itk_source)
    linux_builder.run()
    ran = _wire_run(linux_builder, tmp_path, ipp_dir, itk_source, version="6.0b4")
    linux_builder.run()
    assert ran == ["01_superbuild", "02_build_itk", "03_build_wheels"]


@pytest.fixture
def module_source(tmp_path):
    module = tmp_path / "ITKFoo"
    module.mkdir()
    _git(module, "init", "--quiet", "--initial-branch=main")
    _git(module, "config", "user.email", "test@example.com")
    _git(module, "config", "user.name", "Test")
    (module / "CMakeLists.txt").write_text("project(Foo)\n")
    _git(module, "add", "CMakeLists.txt")
    _git(module, "commit", "--quiet", "-m", "first")
    return module


def test_module_state_follows_commits_and_uncommitted_edits(module_source):
    first = module_source_state(module_source)
    (module_source / "CMakeLists.txt").write_text("project(Foo2)\n")
    edited = module_source_state(module_source)
    assert edited != first
    _git(module_source, "commit", "--quiet", "-am", "second")
    committed = module_source_state(module_source)
    assert committed not in (first, edited)


def test_module_state_ignores_what_the_module_build_writes(module_source):
    before = module_source_state(module_source)
    (module_source / "dist").mkdir()
    (module_source / "dist" / "itk_foo-1.0-cp311-abi3-linux_x86_64.whl").write_text("")
    (module_source / "pyproject.toml.whl").write_text("")
    assert module_source_state(module_source) == before


def test_module_state_without_a_repository_hashes_the_sources(tmp_path):
    module = tmp_path / "ITKFoo"
    (module / "include").mkdir(parents=True)
    (module / "include" / "itkFoo.h").write_text("int a;\n")
    before = module_source_state(module)
    (module / "dist").mkdir()
    (module / "dist" / "foo.whl").write_text("")
    assert module_source_state(module) == before
    (module / "include" / "itkFoo.h").write_text("int b;\n")
    assert module_source_state(module) != before


def test_a_changed_module_runs_every_step_again(
    linux_builder, tmp_path, ipp_dir, itk_source, module_source
):
    _wire_run(linux_builder, tmp_path, ipp_dir, itk_source, module=module_source)
    linux_builder.run()
    ran = _wire_run(linux_builder, tmp_path, ipp_dir, itk_source, module=module_source)
    linux_builder.run()
    assert ran == []
    (module_source / "CMakeLists.txt").write_text("project(Foo2)\n")
    ran = _wire_run(linux_builder, tmp_path, ipp_dir, itk_source, module=module_source)
    linux_builder.run()
    assert ran == ["01_superbuild", "02_build_itk", "03_build_wheels"]
