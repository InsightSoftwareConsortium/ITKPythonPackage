"""The step table drives BuildManager; its keys are what the step log records.

A ``_skipped`` key mapped to a no-op is how a consciously bypassed stage is
made visible in ``build_log_<env>.json``.
"""

from pathlib import Path


def _configure(
    builder,
    *,
    skip_itk_build=False,
    skip_itk_wheel_build=False,
    module=None,
    module_itk_dir="build",
):
    builder.skip_itk_build = skip_itk_build
    builder.skip_itk_wheel_build = skip_itk_wheel_build
    builder.module_source_dir = Path(module) if module else None
    builder.module_itk_dir = module_itk_dir
    builder.build_itk_tarball_cache = False
    builder.cleanup = False
    builder.itk_module_deps = None
    return builder


def test_full_build_registers_every_stage(linux_builder):
    keys = list(_configure(linux_builder).build_step_table())
    assert keys == [
        "01_superbuild_support_components",
        "02_build_wrapped_itk_cplusplus",
        "03_build_wheels",
        "04_post_build_fixup",
        "05_final_import_test",
        "06_build_external_module_wheel_skipped",
    ]


def test_skipping_itk_wheels_also_skips_the_stages_that_need_them(linux_builder):
    """T7: the remote-module path takes ITK from a cache that excludes wheels.

    Step 04 repairs the ITK wheels and step 05 pip-installs them from dist/;
    with step 03 skipped there are none, and 05 aborted the run before the
    module wheel in 06 was ever built.
    """
    builder = _configure(
        linux_builder,
        skip_itk_build=True,
        skip_itk_wheel_build=True,
        module="BioCell",
    )
    keys = list(builder.build_step_table())
    assert keys == [
        "01_superbuild_support_components",
        "02_build_wrapped_itk_cplusplus_skipped",
        "03_build_wheels_skipped",
        "04_post_build_fixup_skipped",
        "05_final_import_test_skipped",
        "06_install_wrapped_itk_cplusplus_skipped",
        "06_build_external_module_wheel_BioCell",
    ]


def test_skipped_stages_are_noops(linux_builder):
    table = _configure(linux_builder, skip_itk_wheel_build=True).build_step_table()
    for name in (
        "03_build_wheels_skipped",
        "04_post_build_fixup_skipped",
        "05_final_import_test_skipped",
    ):
        assert table[name]() is None


def test_skipping_only_the_itk_build_keeps_the_wheel_stages(linux_builder):
    """Skipping the C++ build alone still builds, repairs and tests wheels."""
    keys = list(_configure(linux_builder, skip_itk_build=True).build_step_table())
    assert "02_build_wrapped_itk_cplusplus_skipped" in keys
    assert "03_build_wheels" in keys
    assert "04_post_build_fixup" in keys
    assert "05_final_import_test" in keys


def test_module_step_is_named_after_the_module_directory(linux_builder):
    keys = list(_configure(linux_builder, module="/src/ITKFoo").build_step_table())
    assert keys[-1] == "06_build_external_module_wheel_ITKFoo"


def test_installed_itk_adds_an_install_step_right_before_the_module(linux_builder):
    """module_itk_dir="install": the install tree must exist before step 06
    configures the module against it, so the install is its own recorded
    step immediately ahead of the module step."""
    builder = _configure(
        linux_builder,
        skip_itk_build=True,
        skip_itk_wheel_build=True,
        module="BioCell",
        module_itk_dir="install",
    )
    table = builder.build_step_table()
    keys = list(table)
    assert keys[-2:] == [
        "06_install_wrapped_itk_cplusplus",
        "06_build_external_module_wheel_BioCell",
    ]
    assert table["06_install_wrapped_itk_cplusplus"] == (
        builder.install_wrapped_itk_cplusplus
    )


def test_build_tree_module_records_the_install_step_as_skipped(linux_builder):
    table = _configure(linux_builder, module="BioCell").build_step_table()
    assert table["06_install_wrapped_itk_cplusplus_skipped"]() is None
    assert "06_install_wrapped_itk_cplusplus" not in table


def test_no_module_means_no_install_step_at_all(linux_builder):
    """Nothing but a module consumes the install tree."""
    keys = list(_configure(linux_builder, module_itk_dir="install").build_step_table())
    assert not any(k.startswith("06_install") for k in keys)
