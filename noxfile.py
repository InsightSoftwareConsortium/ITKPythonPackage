#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["nox>=2025.10.16"]
# ///
"""Developer tasks. Wheel builds stay pixi tasks (``pixi run -e <env> build-itk-wheels``)."""

from __future__ import annotations

import argparse
from pathlib import Path

import nox

nox.needs_version = ">=2025.10.16"
nox.options.default_venv_backend = "uv|virtualenv"

DIR = Path(__file__).parent.resolve()
PYPROJECT = nox.project.load_toml(DIR / "pyproject.toml")
DOCS_REQUIREMENTS = DIR / "docs" / "requirements-docs.txt"


@nox.session(reuse_venv=True)
def lint(session: nox.Session) -> None:
    """Run the pre-commit hooks on every file."""
    session.install("pre-commit")
    session.run(
        "pre-commit", "run", "--all-files", "--show-diff-on-failure", *session.posargs
    )


@nox.session(python=["3.11", "3.12", "3.13", "3.14"])
def tests(session: nox.Session) -> None:
    """Run the unit tests; the root pyproject.toml is configuration, not a package."""
    session.install(*nox.project.dependency_groups(PYPROJECT, "dev"))
    session.run("pytest", *session.posargs)


@nox.session(reuse_venv=True, default=False)
def docs(session: nox.Session) -> None:
    """Build the docs as CI does. Pass ``--serve`` to rebuild on change."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="Serve after building")
    parser.add_argument("-b", dest="builder", default="html", help="Sphinx builder")
    args, posargs = parser.parse_known_args(session.posargs)
    serve = args.builder == "html" and args.serve and session.interactive

    session.install("-r", str(DOCS_REQUIREMENTS))
    if serve:
        session.install("sphinx-autobuild")

    out = f"docs/_build/{args.builder}"
    shared_args = ("-b", args.builder, "docs", out, *posargs)
    if serve:
        session.run("sphinx-autobuild", "--open-browser", *shared_args)
    else:
        session.run("sphinx-build", "-W", "--keep-going", *shared_args)


if __name__ == "__main__":
    nox.main()
