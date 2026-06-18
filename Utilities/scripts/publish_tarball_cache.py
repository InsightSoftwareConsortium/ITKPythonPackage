"""Upload ITK build cache tarballs to a GitHub Release.

Usage:
    pixi run -e publish publish-tarball-cache --itk-package-version v6.0b02
    pixi run -e publish publish-tarball-cache --itk-package-version v6.0b02 --create-release

Authentication:
    Set the GH_TOKEN environment variable, or run `gh auth login` beforehand.

Cache files are expected at {build-dir-root}/../ITKPythonBuilds-*.tar.zst (POSIX)
or {build-dir-root}/ITKPythonBuilds-*.zip (Windows).
"""

import argparse
import subprocess
import sys
from pathlib import Path

ITKPYTHONBUILDS_REPO = "InsightSoftwareConsortium/ITKPythonBuilds"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload tarball caches to a GitHub Release on ITKPythonBuilds"
    )
    parser.add_argument(
        "--build-dir-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent
        / "ITKPythonPackage-build",
        help="Root of the build directory (tarballs are in its parent). Default: ../ITKPythonPackage-build",
    )
    parser.add_argument(
        "--itk-package-version",
        required=True,
        help="Release tag name, e.g. v6.0b02",
    )
    parser.add_argument(
        "--repo",
        default=ITKPYTHONBUILDS_REPO,
        help=f"GitHub repository for the release (default: {ITKPYTHONBUILDS_REPO})",
    )
    parser.add_argument(
        "--create-release",
        action="store_true",
        help="Create the GitHub release if it does not already exist",
    )
    args = parser.parse_args()

    build_directory = Path(args.build_dir_root)
    tarball_dir = build_directory.parent
    # POSIX builds produce .tar.zst, Windows builds produce .zip in the build directory
    tarballs = sorted(
        list(tarball_dir.glob("ITKPythonBuilds-*.tar.zst"))
        + list(
            build_directory.glob("ITKPythonBuilds-*.zip")
        )  # Windows builds will be in the build directory
    )

    if not tarballs:
        print(
            f"Error: No ITKPythonBuilds-*.tar.zst or .zip files found in {tarball_dir} or {build_directory}.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Found {len(tarballs)} cache file(s) in {tarball_dir} and {build_directory}:"
    )
    for tb in tarballs:
        size_mb = tb.stat().st_size / (1024 * 1024)
        print(f"  {tb.name} ({size_mb:.1f} MB)")

    tag = args.itk_package_version

    # Check if the release exists
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", args.repo],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if args.create_release:
            print(f"\nCreating release '{tag}' on {args.repo}...")
            create_result = subprocess.run(
                [
                    "gh",
                    "release",
                    "create",
                    tag,
                    "--repo",
                    args.repo,
                    "--title",
                    tag,
                    "--notes",
                    f"ITK Python build cache for {tag}",
                ],
            )
            if create_result.returncode != 0:
                print("Error: Failed to create release.", file=sys.stderr)
                return 1
        else:
            print(
                f"Error: Failed to create release with code: {result.returncode}\nwith message:\n{result.stderr}",
                file=sys.stderr,
            )
            return 1
    else:
        print(f"\nRelease '{tag}' exists on {args.repo}.")

    # Upload each tarball (--clobber replaces existing assets with the same name)
    for tb in tarballs:
        print(f"Uploading {tb.name}...")
        upload_result = subprocess.run(
            ["gh", "release", "upload", tag, str(tb), "--repo", args.repo, "--clobber"],
        )
        if upload_result.returncode != 0:
            print(f"Error: Failed to upload {tb.name}.", file=sys.stderr)
            return 1

    print("\nAll uploads complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
