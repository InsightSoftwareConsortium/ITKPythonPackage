"""Upload ITK Python wheels to PyPI or TestPyPI.

Usage:
    pixi run -e publish publish-wheels --dist-directory /path/to/dist
    pixi run -e publish publish-wheels --dist-directory /path/to/dist --test

Authentication:
    Set TWINE_USERNAME and TWINE_PASSWORD environment variables.
    For token-based auth:
        TWINE_USERNAME=__token__
        TWINE_PASSWORD=pypi-<your-token>

    Alternatively, configure ~/.pypirc (see .pypirc.example in the repo root)
    and name its section with --repository, e.g. --repository testpypi.
"""

import argparse
import subprocess
import sys
from pathlib import Path

TESTPYPI_URL = "https://test.pypi.org/legacy/"


def upload_command(args: argparse.Namespace, wheels: list[Path]) -> list[str]:
    """The ``twine upload`` command for *wheels* to the index *args* names."""
    cmd = ["twine", "upload"]
    if args.repository:
        cmd += ["--repository", args.repository]
    elif args.repository_url:
        cmd += ["--repository-url", args.repository_url]
    elif args.test:
        cmd += ["--repository-url", TESTPYPI_URL]
    if args.skip_existing:
        cmd.append("--skip-existing")
    return cmd + [str(w) for w in wheels]


def upload_target(args: argparse.Namespace) -> str:
    """How the upload destination is shown to the user."""
    if args.repository:
        return f"the ~/.pypirc repository {args.repository!r}"
    return args.repository_url or (TESTPYPI_URL if args.test else "PyPI")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upload ITK wheels to PyPI or TestPyPI"
    )
    parser.add_argument(
        "--dist-directory",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent
        / "ITKPythonPackage-build/dist",
        help="Root of the build dist directory containing dist/*.whl (default: ../ITKPythonPackage-build/dist)",
    )
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--test",
        action="store_true",
        help="Upload to TestPyPI instead of production PyPI",
    )
    destination.add_argument(
        "--repository",
        type=str,
        default=None,
        help="Repository section of ~/.pypirc to upload to, with its credentials "
        "(e.g. testpypi)",
    )
    destination.add_argument(
        "--repository-url",
        type=str,
        default=None,
        help="Custom repository URL",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip wheels that have already been uploaded",
    )
    args = parser.parse_args(argv)

    dist_dir = args.dist_directory
    wheels = sorted(dist_dir.glob("*.whl"))

    if not wheels:
        print(f"Error: No .whl files found in {dist_dir}", file=sys.stderr)
        return 1

    print(f"Found {len(wheels)} wheel(s) in {dist_dir}:")
    for w in wheels:
        print(f"  {w.name}")

    # PyPI rejects plain linux_* platform tags; only manylinux/musllinux wheels are uploadable.
    non_portable = [
        w
        for w in wheels
        if any(tag.startswith("linux_") for tag in w.stem.split("-")[-1].split("."))
    ]
    if non_portable:
        print(
            "Error: these wheels have a linux_* platform tag and cannot be uploaded "
            "to PyPI. Rebuild them with a manylinux228-py* environment:",
            file=sys.stderr,
        )
        for w in non_portable:
            print(f"  {w.name}", file=sys.stderr)
        return 1

    # Validate wheel metadata before uploading
    print("\nRunning twine check...")
    result = subprocess.run(
        ["twine", "check", *(str(w) for w in wheels)],
        check=False,
    )
    if result.returncode != 0:
        print(
            "Error: twine check failed. Fix metadata issues before uploading.",
            file=sys.stderr,
        )
        return 1

    print(f"\nUploading to {upload_target(args)}...")
    result = subprocess.run(upload_command(args, wheels), check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
