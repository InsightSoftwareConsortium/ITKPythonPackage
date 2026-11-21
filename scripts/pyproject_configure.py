#!/usr/bin/env python
import argparse
import os
import re
import shutil
import sys
import textwrap
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from packaging.version import Version
from wheel_builder_utils import read_env_file

# One cp311-abi3 wheel per platform, installable on 3.11 and newer. Pinned
# rather than derived from the interpreter running this driver.
STABLE_ABI_TAG = "cp311"


def parameter_option(key: str, option: str) -> int:
    """Return a formatting option for a template parameter.

    Parameters
    ----------
    key : str
        Template parameter name (e.g. ``'PYPROJECT_PY_MODULES'``).
    option : str
        Option to look up (``'indent'``, ``'newline_if_set'``,
        ``'newline_indent'``, or ``'remove_line_if_empty'``).

    Returns
    -------
    int or bool
        The option value from ``parameter_options`` if defined,
        otherwise the default from ``parameter_option_defaults``.
    """
    parameter_option_defaults = {
        "indent": 0,
        "newline_if_set": False,
        "newline_indent": 0,
        "remove_line_if_empty": False,
    }

    parameter_options = {
        "PYPROJECT_PY_MODULES": {
            "indent": 8,
            "newline_if_set": True,
            "newline_indent": 4,
        },
        "PYPROJECT_DEPENDENCIES": {"indent": 8, "remove_line_if_empty": True},
    }

    default = parameter_option_defaults[option]
    if key not in parameter_options:
        return default
    return parameter_options[key].get(option, default)


def list_to_str(list_: Iterable[str], newline: bool = True) -> str:
    """Join a list of strings as quoted, comma-separated items.

    Parameters
    ----------
    list_ : list[str]
        Items to format.
    newline : bool, optional
        Use newline separators when True, spaces when False.

    Returns
    -------
    str
        Formatted string like ``'"a",\\n"b"'``.
    """
    sep = ", "
    if newline:
        sep = ",\n"
    return sep.join([f'"{item}"' for item in list_])


def configure(
    template_file: str | Path, parameters: Mapping[str, Any], output_file: str | Path
) -> None:
    """Substitute ``@KEY@`` placeholders in *template_file* and write *output_file*.

    Parameters
    ----------
    template_file : str or Path
        Input template containing ``@KEY@`` placeholders.
    parameters : dict[str, str]
        Mapping of placeholder names to substitution values.
    output_file : str or Path
        Destination path for the configured file.
    """
    updated_lines = []
    with Path(template_file).open() as file_:
        lines = file_.readlines()
        for template_line in lines:
            line = template_line
            append = True
            for key in parameters:
                value = str(parameters[key]).strip()
                if (
                    key in line
                    and not value
                    and parameter_option(key, "remove_line_if_empty")
                ):
                    append = False
                    break
                block_indent = " " * parameter_option(key, "indent")
                value = textwrap.indent(value, block_indent)
                newline_indent = " " * parameter_option(key, "newline_indent")
                if value.strip() and parameter_option(key, "newline_if_set"):
                    value = f"\n{value}\n{newline_indent}"
                # TOML strings need each backslash of a value (Windows paths) escaped once.
                value = value.replace("\\", "\\\\")
                line = line.replace(f"@{key}@", value)
            if append:
                updated_lines.append(line)

    with Path(output_file).open("w") as file_:
        file_.writelines(updated_lines)


def from_group_to_wheel(group: str) -> str:
    """Convert an ITK group name to its wheel package name.

    Parameters
    ----------
    group : str
        ITK group name (e.g. ``'Core'``, ``'Filtering'``).

    Returns
    -------
    str
        Wheel name like ``'itk-core'``.
    """
    return f"itk-{group.lower()}"


def update_wheel_pyproject_toml_parameters(
    base_params: dict[str, Any],
    package_env_config: dict[str, Any],
    script_name: str,
    wheel_names: list[str],
    wheel_dependencies: dict[str, Any],
):
    """Build a mapping of wheel name to ``pyproject.toml`` template parameters.

    This is a pure transformation and does not mutate global state.

    Parameters
    ----------
    base_params : dict
        Shared base parameters common to all wheels.
    package_env_config : dict
        Build environment configuration (ITK paths, versions, etc.).
    script_name : str
        Name of the calling script, embedded in the generator field.
    wheel_names : list[str]
        Ordered list of wheel package names to generate parameters for.
    wheel_dependencies : dict[str, list[str]]
        Mapping from wheel name to its dependency list.

    Returns
    -------
    dict[str, dict]
        ``{wheel_name: parameters_dict}`` for each wheel.
    """
    pyproject_py_parameters = {}
    for wheel_name in wheel_names:
        params = dict(base_params)

        # generator
        params["PYPROJECT_GENERATOR"] = f"python {script_name} '{wheel_name}'"

        # name
        if wheel_name == "itk-meta":
            params["PYPROJECT_NAME"] = "itk"
            params["PYPROJECT_PLATLIB"] = r"false"
        else:
            params["PYPROJECT_NAME"] = wheel_name

        # cmake_args
        params["PYPROJECT_CMAKE_ARGS"] = list_to_str(
            [
                f"-DITK_SOURCE_DIR={package_env_config['ITK_SOURCE_DIR']}",
                f"-DITK_GIT_TAG:STRING={package_env_config['ITK_GIT_TAG']}",
                f"-DITK_PACKAGE_VERSION:STRING={package_env_config['ITK_PACKAGE_VERSION']}",
                "-DITK_WRAP_unsigned_short:BOOL=ON",
                "-DITK_WRAP_double:BOOL=ON",
                "-DITK_WRAP_complex_double:BOOL=ON",
                "-DITK_WRAP_IMAGE_DIMS:STRING=2;3;4",
                "-DITK_WRAP_DOC:BOOL=ON",
                f"-DITKPythonPackage_WHEEL_NAME:STRING={wheel_name}",
            ],
            True,
        )

        # install_requires
        wheel_depends = list(wheel_dependencies[wheel_name])

        # py_modules
        if wheel_name != "itk-core":
            params["PYPROJECT_PY_MODULES"] = r""
        else:
            wheel_depends.append("numpy")

        params["PYPROJECT_DEPENDENCIES"] = list_to_str(wheel_depends)

        pyproject_py_parameters[wheel_name] = params

    return pyproject_py_parameters


def get_wheel_names(build_wheels_support_dir: str | Path):
    """Read the ordered list of wheel names from ``WHEEL_NAMES.txt``.

    Parameters
    ----------
    build_wheels_support_dir : str
        Directory containing ``WHEEL_NAMES.txt``.

    Returns
    -------
    list[str]
        Stripped wheel names, one per line.
    """
    with (Path(build_wheels_support_dir) / "WHEEL_NAMES.txt").open() as _file:
        return [wheel_name.strip() for wheel_name in _file]


def get_py_api() -> str:
    """Return the pinned stable-ABI tag.

    Returns
    -------
    str
        ``STABLE_ABI_TAG``.
    """
    return STABLE_ABI_TAG


def get_wheel_dependencies(
    script_dir: str | Path, version: str, wheel_names: list[str]
):
    """Parse ITK CMake files to build a wheel dependency graph.

    Parameters
    ----------
    script_dir : str
        Path to the ``scripts/`` directory.
    version : str
        PEP 440 version string pinned in each dependency.
    wheel_names : list[str]
        All known wheel names; used to build the ``itk-meta`` entry.

    Returns
    -------
    dict[str, list[str]]
        Mapping of wheel name to its list of pinned dependencies.
    """
    all_depends = {}
    regex_group_depends = (
        r"set\s*\(\s*ITK\_GROUP\_([a-zA-Z0-9\_\-]+)\_DEPENDS\s*([a-zA-Z0-9\_\-\s]*)\s*"
    )
    pattern = re.compile(regex_group_depends)
    with (
        Path(script_dir) / ".." / "cmake" / "ITKPythonPackage_BuildWheels.cmake"
    ).open() as file_:
        for line in file_:
            match = re.search(pattern, line)
            if not match:
                continue
            wheel = from_group_to_wheel(match.group(1))
            _wheel_depends = [
                from_group_to_wheel(group) + "==" + version
                for group in match.group(2).split()
            ]
            all_depends[wheel] = _wheel_depends
    all_depends["itk-meta"] = [
        wheel_name + "==" + version
        for wheel_name in wheel_names
        if wheel_name != "itk-meta"
    ]
    all_depends["itk-meta"].append("numpy")
    return all_depends


def build_base_pyproject_parameters(
    package_env_config: dict[str, Any], script_name: str, itk_package_version: str
):
    """Return the base ``pyproject.toml`` template parameters for ITK.

    Parameters
    ----------
    package_env_config : dict
        Build environment configuration.
    script_name : str
        Name of the calling script.
    itk_package_version : str
        PEP 440 version string for the ITK packages.

    Returns
    -------
    dict[str, str]
        Base parameter mapping shared across all wheel configurations.
    """
    # The string is written into pyproject.toml; keep its separators unchanged.
    itk_source_readme: str = os.path.join(  # noqa: PTH118
        package_env_config["ITK_SOURCE_DIR"], "README.md"
    )
    return {
        "PYPROJECT_GENERATOR": f"python {script_name} 'itk'",
        "PYPROJECT_NAME": r"itk",
        "PYPROJECT_VERSION": itk_package_version,
        "PYPROJECT_CMAKE_ARGS": r"",
        "PYPROJECT_PY_API": get_py_api(),
        "PYPROJECT_PLATLIB": r"true",
        "ITK_SOURCE_DIR": package_env_config["ITK_SOURCE_DIR"],
        "ITK_SOURCE_README": itk_source_readme,
        "PYPROJECT_PY_MODULES": list_to_str(
            [
                "itkBase",
                "itkConfig",
                "itkExtras",
                "itkHelpers",
                "itkLazy",
                "itkTemplate",
                "itkTypes",
                "itkVersion",
                "itkBuildOptions",
            ]
        ),
        "PYPROJECT_DOWNLOAD_URL": r"https://github.com/InsightSoftwareConsortium/ITK/releases",
        "PYPROJECT_DESCRIPTION": r"ITK is an open-source toolkit for multidimensional image analysis",
        "PYPROJECT_EXTRA_KEYWORDS": r'"scientific", "medical", "image", "imaging"',
        "PYPROJECT_DEPENDENCIES": r"",
    }


def main() -> None:
    # Parse arguments
    script_dir = Path(__file__).parent
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="""CLI allowing to configure ``pyproject.toml`` found in the `` ITKPythonPackage ``
source tree.

Different versions of ``pyproject.toml`` can be generated based on the value
of the `wheel_name` positional parameter.

Usage::

    pyproject_configure.py [-h] --env-file ENV_FILE [--output-dir OUTPUT_DIR]
                           [--build-dir-root BUILD_DIR_ROOT] wheel_name

    positional arguments:
      wheel_name

    optional arguments:
      -h, --help   show this help message and exit
      --env-file ENV_FILE
                            KEY=VALUE file holding the build configuration
      --output-dir OUTPUT_DIR
                            Output directory for configured 'pyproject.toml'
                            (default: /work)

Accepted values for `wheel_name` are ``itk`` and all values read from
``WHEEL_NAMES.txt``.
""",
    )
    parser.add_argument("wheel_name")
    parser.add_argument(
        "--env-file",
        type=str,
        required=True,
        help="KEY=VALUE file holding the build configuration.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for configured 'pyproject.toml'",
        default=str((Path(script_dir) / "..").resolve()),
    )
    parser.add_argument(
        "--build-dir-root",
        type=str,
        default=f"{script_dir}/../",
        help="The root of the build resources.",
    )
    args = parser.parse_args()
    print(f"Reading configuration settings from {args.env_file}")
    package_env_config = read_env_file(args.env_file, args.build_dir_root)

    configure_one_pyproject_file(
        script_dir, package_env_config, args.output_dir, args.wheel_name
    )


def configure_one_pyproject_file(
    script_dir: str | Path, package_env_config, output_dir, wheel_name: str = "itk"
):
    """Generate a configured ``pyproject.toml`` for a single wheel.

    Parameters
    ----------
    script_dir : str or Path
        Path to the ``scripts/`` directory containing templates.
    package_env_config : dict
        Build environment configuration.
    output_dir : str or Path
        Directory where ``pyproject.toml`` will be written.
    wheel_name : str, optional
        Which wheel to configure (default ``'itk'``).
    """
    # Version needs to be python PEP 440 compliant (no leading v)
    pep440_version: str = package_env_config["ITK_PACKAGE_VERSION"].removeprefix("v")
    try:
        Version(
            pep440_version
        )  # Raise InvalidVersion exception if not PEP 440 compliant
    except ValueError:
        print(f"Invalid PEP 440 version: {pep440_version}")
        sys.exit(1)

    # Resolve script information locally

    build_wheels_support_dir = Path(script_dir) / ".." / "BuildWheelsSupport"
    script_name = Path(__file__).name
    # Write itkVersion.py file to report ITK version in python.
    write_itkVersion_py(Path(output_dir) / "itkVersion.py", pep440_version)
    # Copy LICENSE file needed for each wheel
    shutil.copy(Path(build_wheels_support_dir) / "LICENSE", output_dir)

    base_params = build_base_pyproject_parameters(
        package_env_config, script_name, pep440_version
    )

    wheel_names = get_wheel_names(build_wheels_support_dir)
    wheel_dependencies = get_wheel_dependencies(
        script_dir, base_params["PYPROJECT_VERSION"], wheel_names
    )

    pyproject_py_parameters = {"itk": dict(base_params)}
    pyproject_py_parameters.update(
        update_wheel_pyproject_toml_parameters(
            base_params,
            package_env_config,
            script_name,
            wheel_names,
            wheel_dependencies,
        )
    )

    if wheel_name not in pyproject_py_parameters:
        print(f"Unknown wheel name '{wheel_name}'")
        sys.exit(1)

    # Configure 'pyproject.toml'
    output_file = Path(output_dir) / "pyproject.toml"
    print(f"Generating: {output_file}")
    template = Path(script_dir) / "pyproject.toml.in"
    configure(template, pyproject_py_parameters[wheel_name], output_file)


def write_itkVersion_py(filename: str | Path, itk_package_version: str):
    """Write an ``itkVersion.py`` file reporting the ITK package version.

    Parameters
    ----------
    filename : str or Path
        Output file path.
    itk_package_version : str
        PEP 440 version string to embed.
    """
    itk_version_python_code = f"""
VERSION: str = '{itk_package_version}'

def get_versions() -> str:
    \"\"\"Returns versions for the ITK Python package.

    from itkVersion import get_versions

    # Returns the ITK repository version
    get_versions()['version']

    # Returns the package version. Since GitHub Releases do not support the '+'
    # character in file names, this does not contain the local version
    # identifier in nightly builds, i.e.
    #
    #  '6.0.1.dev20251126'
    #
    # instead of
    #
    #  '6.0.1.dev20251126+139.g922f2d9'
    get_versions()['package-version']
    \"\"\"

    versions = {{}}
    versions['version'] = VERSION
    versions['package-version'] = VERSION.split('+')[0]
    return versions
"""
    with Path(filename).open("w") as wfid:
        wfid.write(itk_version_python_code)


if __name__ == "__main__":
    main()
