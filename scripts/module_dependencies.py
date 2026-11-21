import contextlib
import os
import re
import shutil
import tomllib
from collections.abc import Callable, Iterable
from pathlib import Path


def update_module_itk_deps(pyproject_path: Path, itk_version: str) -> bool:
    """Rewrite ITK dependency pins in a remote module's pyproject.toml.

    Replaces hard-coded ITK sub-package version pins (e.g.
    ``itk-io == 5.4.*``) with a pin matching the ITK version being
    built against (e.g. ``itk-io >= 5.4``).  This ensures that
    wheels produced for ITK 6 can be installed alongside ITK 6
    packages without pip dependency conflicts.

    The rewrite is idempotent: applying it twice yields the same file
    as applying it once.

    Parameters
    ----------
    pyproject_path : Path
        Path to the module's ``pyproject.toml``.
    itk_version : str
        The ITK PEP 440 version string being built (e.g. ``6.0.0b2``).
        Used to compute the minimum major version for the ``>=`` pin.

    Returns
    -------
    bool
        *True* if any dependency was rewritten.
    """
    with Path(pyproject_path).open("rb") as f:
        pyproject_data = tomllib.load(f)

    # --- Strategy 3: module declares dynamic dependencies -----------------
    dynamic_fields = pyproject_data.get("project", {}).get("dynamic", [])
    if "dependencies" in dynamic_fields:
        # The itk-build-metadata provider writes Requires-Dist from ITK_PACKAGE_VERSION.
        os.environ["ITK_PACKAGE_VERSION"] = itk_version
        print(
            f"Strategy 3: {pyproject_path.name} declares "
            f'dynamic=["dependencies"]; set ITK_PACKAGE_VERSION='
            f"{itk_version} for metadata provider"
        )
        return False  # no file modification needed

    # --- Strategy 1: build-time rewrite (fallback) ------------------------
    text = pyproject_path.read_text(encoding="utf-8")

    # Only ITK's own packages follow the ITK release; remote-module pins are reported.
    itk_base_packages = (
        "itk-core",
        "itk-numerics",
        "itk-io",
        "itk-filtering",
        "itk-filtering-extra",
        "itk-registration",
        "itk-segmentation",
        # Most remote modules depend on the metapackage rather than on the
        # sub-packages; its version tracks the ITK release just the same.
        "itk",
    )
    # Longest first, so "itk" cannot shadow "itk-core" in the alternation.
    _base_pkg_alt = "|".join(
        re.escape(p) for p in sorted(itk_base_packages, key=len, reverse=True)
    )
    # Modules pin either "itk == 5.4.*" or "itk~=5.4.0"; rewrite both forms.
    pattern = re.compile(
        rf'"({_base_pkg_alt})\s*(?:==\s*\d+\.\d+\.\*|~=\s*\d+\.\d+(?:\.\d+)?)"'
    )

    # Warn about pinned remote-module cross-deps that may also need
    # attention but should not be auto-rewritten.
    cross_dep_pattern = re.compile(
        r'"(itk-[a-z][a-z0-9-]*)\s*(?:==\s*\d+\.\d+\.\*|~=\s*\d+\.\d+(?:\.\d+)?)"'
    )
    for m in cross_dep_pattern.finditer(text):
        pkg = m.group(1)
        if pkg not in itk_base_packages:
            print(
                f"  WARNING: {pyproject_path.name} pins remote module "
                f"cross-dep {m.group(0)}: review manually"
            )

    # Pin >= MAJOR.MINOR.0b1 of the ITK linked against (b1 so the series' pre-releases
    # satisfy it under PEP 440) and < the next major, whose ABI differs.
    version_match = re.match(r"v?(\d+)\.(\d+)", itk_version)
    if version_match:
        min_floor = f"{version_match.group(1)}.{version_match.group(2)}.0b1"
        max_exclusive = str(int(version_match.group(1)) + 1)
    else:
        # Not a version (e.g. a branch name): any pin built from it would
        # not be a valid specifier, so leave the module's pins alone.
        print(
            f"  Leaving ITK pins in {pyproject_path.name} unchanged: "
            f"{itk_version!r} is not a MAJOR.MINOR version"
        )
        return False

    changed = False

    def _replace(m: re.Match[str]) -> str:
        nonlocal changed
        changed = True
        pkg = m.group(1)
        return f'"{pkg} >= {min_floor}, < {max_exclusive}"'

    new_text = pattern.sub(_replace, text)
    if changed:
        pyproject_path.write_text(new_text, encoding="utf-8")
        print(
            f"Strategy 1: Updated ITK dependency pins in {pyproject_path} "
            f"(>= {min_floor} for ITK {itk_version})"
        )
    return changed


def copy_files(
    sources: Iterable[Path], destination: Path, source_root: Path | None = None
) -> None:
    """Copy each regular file in *sources* into *destination*.

    A file keeps its path relative to *source_root*, or only its name
    when *source_root* is None.
    """
    for src in sources:
        if src.is_file():
            relative = src.relative_to(source_root) if source_root else Path(src.name)
            dst = destination / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(OSError):
                shutil.copy2(src, dst)


def build_module_dependencies(
    itk_module_deps: str,
    module_source_dir: Path,
    module_dependencies_root_dir: Path | None,
    run: Callable[..., int],
    build_module: Callable[[Path], None],
) -> None:
    """
    Build prerequisite ITK external modules, mirroring the behavior of
    the platform shell scripts that use the ITK_MODULE_PREQ environment.

    *run* executes each git command, as the builder's ``echo_check_call``
    does; *build_module* builds one cloned dependency's wheel.

    Accepted formats in *itk_module_deps* (colon-delimited):
      - "MeshToPolyData@v0.10.0"  -> defaults to
        "InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0"
      - "InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0"

    For each dependency, clone the repository, checkout the given tag,
    build it against the ITK tree this build already uses, then copy
    headers and wrapping input files into the current module tree
    (include/ and wrapping/), similar to the bash implementations.
    The cache is not downloaded or extracted again for a dependency.
    """

    if len(itk_module_deps) == 0:
        return
    print(f"Building module dependencies: {itk_module_deps}")
    if module_dependencies_root_dir is not None:
        module_dependencies_root_dir.mkdir(parents=True, exist_ok=True)

    # Normalize entries to "Org/Repo@Tag"
    def _normalize(entry: str) -> str:
        entry = entry.strip()
        if not entry:
            return ""
        if "/" in entry:
            # Already Org/Repo@Tag
            return entry
        # Short form: Name@Tag -> InsightSoftwareConsortium/ITKName@Tag
        try:
            name, tag = entry.split("@", 1)
        except ValueError:
            # If no tag, pass-through (unexpected)
            return entry
        repo = f"ITK{name}"
        return f"InsightSoftwareConsortium/{repo}@{tag}"

    # Ensure working directories exist
    module_root = Path(module_source_dir).resolve()
    include_dir = module_root / "include"
    wrapping_dir = module_root / "wrapping"
    include_dir.mkdir(parents=True, exist_ok=True)
    wrapping_dir.mkdir(parents=True, exist_ok=True)

    dep_entries = [e for e in (s for s in itk_module_deps.split(":")) if e]
    normalized = [_normalize(e) for e in dep_entries]
    normalized = [e for e in normalized if e]

    # Build each dependency in order
    for _current_entry, entry in enumerate(normalized):
        if len(entry) == 0:
            continue
        print(f"Get dependency module information for {entry}")
        org = entry.split("/", 1)[0]
        repo_tag = entry.split("/", 1)[1]
        repo = repo_tag.split("@", 1)[0]
        tag = repo_tag.split("@", 1)[1] if "@" in repo_tag else ""

        upstream = f"https://github.com/{org}/{repo}.git"
        dependent_module_clone_dir = (
            module_dependencies_root_dir / repo
            if module_dependencies_root_dir
            else module_root / repo
        )
        if not dependent_module_clone_dir.exists():
            run(
                ["git", "clone", upstream, dependent_module_clone_dir],
                check=True,
            )

        # Checkout requested tag
        run(
            [
                "git",
                "-C",
                dependent_module_clone_dir,
                "fetch",
                "--all",
                "--tags",
            ],
            check=True,
        )
        if tag:
            run(
                ["git", "-C", dependent_module_clone_dir, "checkout", tag],
                check=True,
            )

        if (dependent_module_clone_dir / "setup.py").exists():
            msg: str = f"Old sci-kit-build with setup.py is no longer supported for {dependent_module_clone_dir} at {tag}"
            raise RuntimeError(msg)

        build_module(Path(dependent_module_clone_dir))

        # After building dependency, copy includes and wrapping files
        # 1) Top-level include/* -> include/
        dep_include = dependent_module_clone_dir / "include"
        if dep_include.exists():
            copy_files(dep_include.rglob("*"), include_dir, dep_include)

        # 2) Any */build/*/include/* -> include/
        for sub in dependent_module_clone_dir.rglob("*build*/**/include"):
            if sub.is_dir():
                copy_files(sub.rglob("*"), include_dir, sub)

        # 3) Wrapping templates (*.in, *.init) -> wrapping/
        dep_wrapping = dependent_module_clone_dir / "wrapping"
        if dep_wrapping.exists():
            for pattern in ("*.in", "*.init"):
                copy_files(dep_wrapping.rglob(pattern), wrapping_dir)
