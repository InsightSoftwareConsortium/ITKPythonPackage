"""Upload ITK Python wheels to PyPI or TestPyPI.

Usage:
    pixi run -e publish publish-wheels --dist-directory /path/to/dist
    pixi run -e publish publish-wheels --dist-directory /path/to/dist --test

Authentication:
    Set TWINE_USERNAME and TWINE_PASSWORD environment variables.
    For token-based auth:
        TWINE_USERNAME=__token__
        TWINE_PASSWORD=pypi-<your-token>

    Alternatively, configure ~/.pypirc (see .pypirc.example in the repo root).
"""

import argparse
import subprocess
import sys
from pathlib import Path

TESTPYPI_URL = "https://test.pypi.org/legacy/"


def main() -> int:
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
    parser.add_argument(
        "--test",
        action="store_true",
        help="Upload to TestPyPI instead of production PyPI",
    )
    parser.add_argument(
        "--repository-url",
        type=str,
        default=None,
        help="Custom repository URL (overrides --test)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip wheels that have already been uploaded",
    )
    args = parser.parse_args()

    dist_dir = args.dist_directory
    wheels = sorted(dist_dir.glob("*.whl"))

    if not wheels:
        print(f"Error: No .whl files found in {dist_dir}", file=sys.stderr)
        return 1

    print(f"Found {len(wheels)} wheel(s) in {dist_dir}:")
    for w in wheels:
        print(f"  {w.name}")

    # Validate wheel metadata before uploading
    print("\nRunning twine check...")
    result = subprocess.run(
        ["twine", "check", *(str(w) for w in wheels)],
    )
    if result.returncode != 0:
        print(
            "Error: twine check failed. Fix metadata issues before uploading.",
            file=sys.stderr,
        )
        return 1

    # Build upload command
    cmd = ["twine", "upload"]
    if args.repository_url:
        cmd += ["--repository-url", args.repository_url]
    elif args.test:
        cmd += ["--repository-url", TESTPYPI_URL]
    if args.skip_existing:
        cmd.append("--skip-existing")
    cmd += [str(w) for w in wheels]

    target = args.repository_url or (TESTPYPI_URL if args.test else "PyPI")
    print(f"\nUploading to {target}...")
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
