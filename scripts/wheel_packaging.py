"""Tarball creation and post-build cleanup for POSIX wheel builds.

These are build-tree operations rather than builder behavior, so they
live outside the builder hierarchy. The two pure helpers at the top
express the path and cleanup rules without invoking ``tar`` or ``zstd``.
"""

from os import environ
from pathlib import Path

from wheel_builder_utils import _remove_tree, get_default_platform_build


def tarball_paths(
    build_dir_root: Path, platform_name: str, arch_postfix: str
) -> tuple[Path, Path]:
    """Return the (uncompressed, zstd) cache paths.

    The cache lives in ``dist/`` because containers mount the build
    tree there; the directory above it is not always mounted.
    """
    tar_name = f"ITKPythonBuilds-{platform_name}-{arch_postfix}.tar"
    output_dir = build_dir_root / "dist"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / tar_name, output_dir / f"{tar_name}.zst"


def remove_uncompressed_tar(tar_path: Path) -> None:
    """Drop the multi-gigabyte .tar once zstd has succeeded."""
    tar_path.unlink(missing_ok=True)


def post_build_cleanup(builder) -> None:
    """Remove intermediate build artifacts, leaving ``dist/`` intact.

    Actions:
    - remove oneTBB-prefix (symlink or dir)
    - remove ITKPythonPackage/, tools/, _skbuild/, build/
    - remove top-level *.egg-info
    - remove ITK-* build tree and tarballs
    - if ITK_MODULE_PREQ is set, remove cloned module dirs
    """
    base = Path(builder.package_env_config["IPP_SOURCE_DIR"])

    def rm(tree_path: Path):
        try:
            _remove_tree(tree_path)
        except Exception:
            pass

    # 1) unlink oneTBB-prefix if it's a symlink or file
    tbb_prefix_dir = base / "oneTBB-prefix"
    try:
        if tbb_prefix_dir.is_symlink() or tbb_prefix_dir.is_file():
            tbb_prefix_dir.unlink(missing_ok=True)  # type: ignore[arg-type]
        elif tbb_prefix_dir.exists():
            rm(tbb_prefix_dir)
    except Exception:
        pass

    # 2) standard build directories
    for rel in ("ITKPythonPackage", "tools", "_skbuild", "build"):
        rm(base / rel)

    # 3) egg-info folders at top-level
    for p in base.glob("*.egg-info"):
        rm(p)

    # 4) ITK build tree and tarballs, both under the build root rather than
    #    the source checkout: ITK-<platform-env>-<pixi-env>_<arch> in build/,
    #    and the cache in dist/.
    target_arch = builder.package_env_config["ARCH"]
    for p in (builder.build_dir_root / "build").glob(f"ITK-*_{target_arch}"):
        rm(p)

    # Tarballs
    for p in (builder.build_dir_root / "dist").glob("ITKPythonBuilds-*.tar*"):
        rm(p)

    # 5) Optional module prerequisites cleanup (ITK_MODULE_PREQ)
    # Format: "InsightSoftwareConsortium/ITKModuleA@v1.0:Kitware/ITKModuleB@sha"
    itk_preq = builder.package_env_config.get("ITK_MODULE_PREQ") or environ.get(
        "ITK_MODULE_PREQ", ""
    )
    if itk_preq:
        for entry in itk_preq.split(":"):
            entry = entry.strip()
            if not entry:
                continue
            try:
                module_name = entry.split("@", 1)[0].split("/", 1)[1]
            except Exception:
                continue
            rm(base / module_name)


def create_posix_tarball(builder) -> None:
    """Create a compressed tarball of the ITK Python build tree.

    Mirrors the historical scripts/*-build-tarball.sh behavior:
    - zstd compress with options (-10 -T6 --long=31)

    Warns if directory structure doesn't match expected layout for GitHub Actions.
    """
    arch_postfix: str = f"{builder.package_env_config['ARCH']}"
    # Fixup platform name for macOS, eventually need to standardize on macosx naming convention
    platform_name: str = get_default_platform_build().split("-")[0]
    itk_packaging_reference_dir = builder.build_dir_root.parent

    tar_path, zst_path = tarball_paths(
        builder.build_dir_root, platform_name, arch_postfix
    )

    itk_resources_build_dir: Path = builder.build_dir_root
    ipp_source_dir: Path = builder.package_env_config["IPP_SOURCE_DIR"]

    # Validate directory structure and determine tarball strategy
    issues = []

    # Try to use relative paths first
    try:
        rel_build = itk_resources_build_dir.relative_to(itk_packaging_reference_dir)
        rel_ipp = ipp_source_dir.relative_to(itk_packaging_reference_dir)
    except ValueError:
        # Fall back to absolute paths
        rel_build = itk_resources_build_dir
        rel_ipp = ipp_source_dir
        itk_packaging_reference_dir = Path(
            "/"
        )  # Tar from root when using absolute paths

    if itk_resources_build_dir.parent != ipp_source_dir.parent:
        issues.append("Build and source dirs are not siblings")

    if ipp_source_dir.name != "ITKPythonPackage":
        issues.append(
            f"Source dir is '{ipp_source_dir.name}', expected 'ITKPythonPackage'"
        )

    # Issue consolidated warning for compatibility issues
    if issues:
        print("\n" + "=" * 70)
        print("WARNING: Tarball will NOT be compatible with GitHub Actions")
        print("=" * 70)
        for issue in issues:
            print(f"  * {issue}")
        print(
            "\nExpected structure: <parent>/{ITKPythonPackage, ITKPythonPackage-build}"
        )
        print(f"Current: Build={itk_resources_build_dir}")
        print(f"         Source={ipp_source_dir}")
        print("\nTarball will be created for local reuse but may not work in CI/CD.")
        print("=" * 70 + "\n")

    # Build tarball include paths
    tarball_include_paths = [
        str(rel_build),
        str(rel_ipp),
    ]

    if tar_path.exists():
        print(f"Removing existing tarball {tar_path}")
        tar_path.unlink()
    if zst_path.exists():
        print(f"Removing existing zstd tarball {zst_path}")
        zst_path.unlink()

    # Create tarball
    builder.echo_check_call(
        [
            "tar",
            "-C",
            str(itk_packaging_reference_dir),
            "-cf",
            str(tar_path),
            "--exclude=*.o",
            "--exclude=*.whl",  # Do not include built wheels
            "--exclude=*/dist/*",  # Do not include the dist whl output directory
            "--exclude=*/wheelbuilds/*",  # Do not include the wheelbuild support directory
            "--exclude=*/__pycache__/*",  # Do not include __pycache__
            "--exclude=install_manifest_*.txt",  # Do not include install manifest files
            "--exclude=._*",  # Exclude mac dot files
            # Exclude the directory itself, not just its contents: a surviving
            # empty .git makes git report "not a repository" rather than the
            # absence a consumer can detect by looking.
            "--exclude=*/.git",
            "--exclude=*/.idea/*",
            "--exclude=*/.pixi/*",
            "--exclude=*/castxml_inputs/*",
            "--exclude=*/Wrapping/Modules/*",
            *tarball_include_paths,
        ],
        check=True,
    )
    if not tar_path.exists() or tar_path.stat().st_size == 0:
        raise RuntimeError(f"tar produced no usable archive at {tar_path}")

    # Compress with zstd
    builder.echo_check_call(
        [
            "zstd",
            "-f",
            "-10",
            "-T6",
            "--long=31",
            str(tar_path),
            "-o",
            str(zst_path),
        ],
        check=True,
    )
    if not zst_path.exists() or zst_path.stat().st_size == 0:
        raise RuntimeError(f"zstd produced no usable archive at {zst_path}")

    remove_uncompressed_tar(tar_path)

    print(f"Tarball created: {zst_path}")
    if issues:
        print("Compatibility warnings above - review before using in CI/CD")
