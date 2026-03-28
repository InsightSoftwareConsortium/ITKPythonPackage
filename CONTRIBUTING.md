# Contributing to ITKPythonPackage

## Getting Started

Clone the repository and install the pre-commit hooks:

```bash
git clone https://github.com/InsightSoftwareConsortium/ITKPythonPackage.git
cd ITKPythonPackage
````

Install [Pixi](https://pixi.sh) for managing the build environment:

```bash
curl -fsSL https://pixi.sh/install.sh | bash
pixi install
```

Install pre-commit hooks

```bash
pixi run pre-commit-install
# optionally run pre-commit hooks
pixi run pre-commit-run
```


## Development Workflow

### Code Style

Pre-commit hooks enforce all formatting and linting automatically on commit:

- **Python**: Black (formatting), Ruff (linting + import sorting)
- **Shell**: ShellCheck (linting), shfmt (formatting)
- **TOML**: Taplo (formatting)

Run against all files manually:

```bash
pre-commit run --all-files
```

### Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org), enforced by Commitizen:

```
feat: add support for Python 3.12 wheels
fix: correct cmake args not propagating to module builds
chore: update pre-commit hook versions
docs: clarify aarch64 build requirements
```

Commitizen will reject commits that don't follow this format.

### Building Docs

```bash
pip install -r docs/requirements-docs.txt
sphinx-build -W -b html docs docs/_build/html
```

## Submitting a Pull Request

1. Create a branch from `main`
2. Make your changes and ensure `pre-commit run --all-files` passes
3. Open a PR, fill out the template, including which platforms you tested on
4. CI will run pre-commit checks automatically

## Questions

For build questions or general ITK support, use the [ITK Discourse forum](https://discourse.itk.org).
