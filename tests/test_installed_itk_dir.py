"""Building a remote module against an *installed* ITK (module_itk_dir="install").

The install tree is a sibling of the build tree, is produced by
``cmake --install``, and is only accepted as ``ITK_DIR`` when it carries the
module build files and wrapping infrastructure a remote module includes.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from build_python_instance_base import BuildPythonInstanceBase
from cmake_argument_builder import CMakeArgumentBuilder


def _wire(builder, tmp_path, *, module_itk_dir):
    builder.module_itk_dir = module_itk_dir
    builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    builder.cmake_itk_source_build_configurations.set(
        "ITK_BINARY_DIR:PATH", (tmp_path / "build" / "ITK-bld").as_posix()
    )
    builder.package_env_config.update(
        {
            "CMAKE_EXECUTABLE": "cmake",
            "PYTHON_EXECUTABLE": "python",
            "BUILD_TYPE": "Release",
        }
    )
    builder.venv_info_dict["python_include_dir"] = str(tmp_path / "inc")
    return builder


def _lay_out_install_tree(prefix: Path, *, with_module_support: bool) -> Path:
    itk_dir = prefix / "lib" / "cmake" / "ITK-6.0"
    itk_dir.mkdir(parents=True)
    (itk_dir / "ITKConfig.cmake").write_text("")
    if with_module_support:
        (itk_dir / "ITKModuleExternal.cmake").write_text("")
        (itk_dir / "Wrapping").mkdir()
        (itk_dir / "Wrapping" / "CMakeLists.txt").write_text("")
    return itk_dir


def test_the_default_is_the_build_tree():
    assert BuildPythonInstanceBase.module_itk_dir == "build"
    assert BuildPythonInstanceBase.MODULE_ITK_DIR_CHOICES == ("build", "install")


def test_install_prefix_is_a_sibling_of_the_build_tree(tmp_path, linux_builder):
    """Inside build/, so a cache of that directory carries the install tree."""
    _wire(linux_builder, tmp_path, module_itk_dir="install")
    assert linux_builder.itk_install_prefix() == tmp_path / "build" / "ITK-bld-install"


def test_installed_itk_dir_requires_an_install_tree(tmp_path, linux_builder):
    _wire(linux_builder, tmp_path, module_itk_dir="install")
    with pytest.raises(RuntimeError, match="No installed ITK"):
        linux_builder.installed_itk_dir()


def test_installed_itk_dir_rejects_an_itk_without_module_support(
    tmp_path, linux_builder
):
    """A stock ITK installs ITKConfig.cmake but not the module build files;
    the module's first include would fail, so say why up front."""
    _wire(linux_builder, tmp_path, module_itk_dir="install")
    _lay_out_install_tree(linux_builder.itk_install_prefix(), with_module_support=False)
    with pytest.raises(RuntimeError) as excinfo:
        linux_builder.installed_itk_dir()
    message = str(excinfo.value)
    assert "ITKModuleExternal.cmake" in message
    assert "ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES" in message


def test_installed_itk_dir_is_the_versioned_cmake_package_dir(tmp_path, linux_builder):
    _wire(linux_builder, tmp_path, module_itk_dir="install")
    itk_dir = _lay_out_install_tree(
        linux_builder.itk_install_prefix(), with_module_support=True
    )
    assert linux_builder.installed_itk_dir() == itk_dir


def test_install_step_runs_cmake_install_into_the_prefix(tmp_path, linux_builder):
    _wire(linux_builder, tmp_path, module_itk_dir="install")
    prefix = linux_builder.itk_install_prefix()
    seen = {}

    def fake_install(cmd, *args, check=False, **kwargs):
        seen["cmd"] = [str(c) for c in cmd]
        seen["check"] = check
        _lay_out_install_tree(prefix, with_module_support=True)
        return 0

    with patch.object(linux_builder, "echo_check_call", side_effect=fake_install):
        linux_builder.install_wrapped_itk_cplusplus()

    assert seen["cmd"] == [
        "cmake",
        "--install",
        (tmp_path / "build" / "ITK-bld").as_posix(),
        "--prefix",
        str(prefix),
    ]
    assert seen["check"] is True


def test_install_step_fails_when_the_install_tree_is_unusable(tmp_path, linux_builder):
    """cmake --install succeeding is not enough: the tree must be one a
    module can be configured against."""
    _wire(linux_builder, tmp_path, module_itk_dir="install")

    def stock_itk_install(cmd, *args, **kwargs):
        _lay_out_install_tree(
            linux_builder.itk_install_prefix(), with_module_support=False
        )
        return 0

    with patch.object(linux_builder, "echo_check_call", side_effect=stock_itk_install):
        with pytest.raises(RuntimeError, match="ITKModuleExternal.cmake"):
            linux_builder.install_wrapped_itk_cplusplus()


def _module_configure_defines(builder, tmp_path) -> list[str]:
    """Run the module build with the tools stubbed out; return its -D list."""
    module = tmp_path / "ITKFoo"
    module.mkdir()
    builder.module_source_dir = module
    seen = {}

    def capture(cmd, *args, **kwargs):
        seen["cmd"] = [str(c) for c in cmd]
        return 0

    with (
        patch.object(builder, "echo_check_call", side_effect=capture),
        patch("build_python_instance_base.verify_stable_abi_wheels", return_value=[]),
    ):
        builder.build_external_module_python_wheel()
    return [c for c in seen["cmd"] if "ITK_DIR" in c]


def test_module_is_configured_against_the_install_tree_when_asked(
    tmp_path, linux_builder
):
    _wire(linux_builder, tmp_path, module_itk_dir="install")
    itk_dir = _lay_out_install_tree(
        linux_builder.itk_install_prefix(), with_module_support=True
    )
    defines = _module_configure_defines(linux_builder, tmp_path)
    assert len(defines) == 1
    # scikit-build-core defines are rendered as cmake.define.<KEY>='<value>'
    assert f"ITK_DIR:PATH='{itk_dir.as_posix()}'" in defines[0]


def test_module_is_configured_against_the_build_tree_by_default(
    tmp_path, linux_builder
):
    _wire(linux_builder, tmp_path, module_itk_dir="build")
    defines = _module_configure_defines(linux_builder, tmp_path)
    assert len(defines) == 1
    build_tree = (tmp_path / "build" / "ITK-bld").as_posix()
    assert f"ITK_DIR:PATH='{build_tree}'" in defines[0]


def test_module_against_a_missing_install_tree_fails_before_configuring(
    tmp_path, linux_builder
):
    """Falling back to the build tree here would silently test the wrong
    thing; the whole point of the mode is that only the install tree is used."""
    _wire(linux_builder, tmp_path, module_itk_dir="install")
    with pytest.raises(RuntimeError, match="No installed ITK"):
        _module_configure_defines(linux_builder, tmp_path)


def test_the_itk_configure_asks_for_the_wrapping_development_files():
    """Every ITK build is configured so its tree can be installed for module
    use later; an ITK without the option just reports it unused."""
    import build_python_instance_base

    text = Path(build_python_instance_base.__file__).read_text()
    assert '"ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES:BOOL": "ON"' in text
