import os
import re
import shutil
import tomllib
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

    .. note:: Strategy 1 (build-time rewrite) — interim solution.

       This approach rewrites the module's pyproject.toml on disk,
       builds the wheel, then restores the original. It works today
       with zero changes to remote modules but is inherently fragile
       (regex-based, modifies the source tree).

       **Plan to migrate to Strategy 3 (scikit-build-core dynamic
       metadata provider):**

       1. Create a small installable package ``itk-build-metadata``
          that implements the scikit-build-core dynamic metadata
          provider interface (see scikit-build-core docs:
          ``tool.scikit-build.metadata.<field>.provider``).

       2. The provider inspects the build environment at wheel-build
          time to discover the ITK version — either from the
          ``ITK_PACKAGE_VERSION`` env var (set by this build system),
          from ``ITKConfig.cmake`` on ``CMAKE_PREFIX_PATH``, or from
          an already-installed ``itk-core`` package.

       3. It emits the correct ``Requires-Dist`` entries (e.g.
          ``itk-io >= 5.4``) into the wheel metadata without
          touching ``pyproject.toml`` on disk at all.

       4. Remote modules opt in by declaring dynamic dependencies::

            [project]
            dynamic = ["dependencies"]

            [tool.scikit-build.metadata.dependencies]
            provider = "itk_build_metadata"
            provider-path = "."   # or from installed package

       5. Roll out incrementally: update ITKModuleTemplate first,
          then migrate existing modules via the ``/update-itk-deps``
          skill (in REMOTE_MODULES/.claude/skills/). Modules that
          have not migrated continue to work via this Strategy 1
          fallback, so both approaches coexist during the transition.

       6. Once all ~60 remote modules have adopted Strategy 3,
          this method can be removed.

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
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)

    # --- Strategy 3: module declares dynamic dependencies -----------------
    dynamic_fields = pyproject_data.get("project", {}).get("dynamic", [])
    if "dependencies" in dynamic_fields:
        # The module has opted into dynamic dependency resolution.
        # Set ITK_PACKAGE_VERSION in the environment so the
        # scikit-build-core metadata provider (itk-build-metadata)
        # can emit the correct Requires-Dist at build time.
        os.environ["ITK_PACKAGE_VERSION"] = itk_version
        print(
            f"Strategy 3: {pyproject_path.name} declares "
            f'dynamic=["dependencies"]; set ITK_PACKAGE_VERSION='
            f"{itk_version} for metadata provider"
        )
        return False  # no file modification needed

    # --- Strategy 1: build-time rewrite (fallback) ------------------------
    text = pyproject_path.read_text(encoding="utf-8")

    # Only rewrite ITK *base* sub-packages whose versions are tied to
    # the ITK release.  Remote module cross-deps (e.g.
    # itk-meshtopolydata == 0.12.*) are versioned independently and
    # must NOT be rewritten — flag them for manual review instead.
    _ITK_BASE_PACKAGES = (
        "itk-core",
        "itk-numerics",
        "itk-io",
        "itk-filtering",
        "itk-registration",
        "itk-segmentation",
        # Most remote modules depend on the metapackage rather than on the
        # sub-packages; its version tracks the ITK release just the same.
        "itk",
    )
    # Longest first, so "itk" cannot shadow "itk-core" in the alternation.
    _base_pkg_alt = "|".join(
        re.escape(p) for p in sorted(_ITK_BASE_PACKAGES, key=len, reverse=True)
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
        if pkg not in _ITK_BASE_PACKAGES:
            print(
                f"  WARNING: {pyproject_path.name} pins remote module "
                f"cross-dep {m.group(0)} — review manually"
            )

    # The minimum version floor is the MAJOR.MINOR of the ITK version
    # being built.  A wheel compiled against ITK 6.0 requires ITK >= 6.0
    # at install time; one compiled against ITK 5.4 requires >= 5.4.
    # The build system itself supports building against any ITK from
    # v5.4 through the latest (v5.5, v6.0, v7.1, etc.) — the floor
    # simply reflects which ITK the wheel was actually linked against.
    # Tags carry a leading "v" and a pre-release or dev suffix
    # (e.g. v6.0rc01.dev20260915), neither of which belongs in the floor:
    # the wheel works with the whole 6.0 series, not one release candidate.
    # The pin is also bounded above: the wheel is compiled against this ITK
    # major series and its ABI, so the next major must not satisfy it.
    # The floor carries an explicit ".0b1" pre-release suffix. PEP 440 sorts
    # pre-releases *below* their final release, so ``6.0.0b2`` does not
    # satisfy ``>= 6.0`` -- the whole 6.0 RC series would be excluded by its
    # own modules, and ``pip install --pre`` cannot rescue it because the
    # ordering, not pre-release visibility, is what fails. Pinning the floor
    # at the earliest pre-release of the series admits 6.0.0b1, the RCs and
    # the final 6.0.0 alike. It also makes --pre unnecessary: a specifier
    # that names a pre-release permits pre-releases for that requirement.
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

    def _replace(m: re.Match) -> str:
        nonlocal changed
        changed = True
        pkg = m.group(1)
        if max_exclusive is None:
            return f'"{pkg} >= {min_floor}"'
        return f'"{pkg} >= {min_floor}, < {max_exclusive}"'

    new_text = pattern.sub(_replace, text)
    if changed:
        pyproject_path.write_text(new_text, encoding="utf-8")
        print(
            f"Strategy 1: Updated ITK dependency pins in {pyproject_path} "
            f"(>= {min_floor} for ITK {itk_version})"
        )
    return changed


def build_module_dependencies(context) -> None:
    """
    Build prerequisite ITK external modules, mirroring the behavior of
    the platform shell scripts that use the ITK_MODULE_PREQ environment.

    Accepted formats in context.itk_module_deps (colon-delimited):
      - "MeshToPolyData@v0.10.0"  -> defaults to
        "InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0"
      - "InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0"

    For each dependency, clone the repository, checkout the given tag,
    build it against the ITK tree this build already uses, then copy
    headers and wrapping input files into the current module tree
    (include/ and wrapping/), similar to the bash implementations.
    The cache is not downloaded or extracted again for a dependency.
    """

    if len(context.itk_module_deps) == 0:
        return
    print(f"Building module dependencies: {context.itk_module_deps}")
    context.module_dependencies_root_dir.mkdir(parents=True, exist_ok=True)

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
    module_root = Path(context.module_source_dir).resolve()
    include_dir = module_root / "include"
    wrapping_dir = module_root / "wrapping"
    include_dir.mkdir(parents=True, exist_ok=True)
    wrapping_dir.mkdir(parents=True, exist_ok=True)

    dep_entries = [e for e in (s for s in context.itk_module_deps.split(":")) if e]
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
        dependant_module_clone_dir = (
            context.module_dependencies_root_dir / repo
            if context.module_dependencies_root_dir
            else module_root / repo
        )
        if not dependant_module_clone_dir.exists():
            context.echo_check_call(
                ["git", "clone", upstream, dependant_module_clone_dir],
                check=True,
            )

        # Checkout requested tag
        context.echo_check_call(
            [
                "git",
                "-C",
                dependant_module_clone_dir,
                "fetch",
                "--all",
                "--tags",
            ],
            check=True,
        )
        if tag:
            context.echo_check_call(
                ["git", "-C", dependant_module_clone_dir, "checkout", tag],
                check=True,
            )

        if (dependant_module_clone_dir / "setup.py").exists():
            msg: str = (
                f"Old sci-kit-build with setup.py is no longer supported for {dependant_module_clone_dir} at {tag}"
            )
            raise RuntimeError(msg)

        # Clone the current build environment and modify for the current module
        dependent_module_build_setup = context.clone()
        dependent_module_build_setup.module_source_dir = Path(
            dependant_module_clone_dir
        )
        dependent_module_build_setup.itk_module_deps = None  # Prevent recursion
        dependent_module_build_setup.run()

        # After building dependency, copy includes and wrapping files
        # 1) Top-level include/* -> include/
        dep_include = dependant_module_clone_dir / "include"
        if dep_include.exists():
            for src in dep_include.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(dep_include)
                    dst = include_dir / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(src, dst)
                    except Exception:
                        pass

        # 2) Any */build/*/include/* -> include/
        for sub in dependant_module_clone_dir.rglob("*build*/**/include"):
            if sub.is_dir():
                for src in sub.rglob("*"):
                    if src.is_file():
                        rel = src.relative_to(sub)
                        dst = include_dir / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(src, dst)
                        except Exception:
                            pass

        # 3) Wrapping templates (*.in, *.init) -> wrapping/
        dep_wrapping = dependant_module_clone_dir / "wrapping"
        if dep_wrapping.exists():
            for pattern in ("*.in", "*.init"):
                for src in dep_wrapping.rglob(pattern):
                    if src.is_file():
                        dst = wrapping_dir / src.name
                        try:
                            shutil.copy2(src, dst)
                        except Exception:
                            pass
