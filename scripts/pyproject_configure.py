#!/usr/bin/env python
import argparse
import os
import re
import shutil
import sys
from pathlib import Path

from packaging.version import Version
from wheel_builder_utils import read_env_file


def parameter_option(key, option):
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
        The option value from ``PARAMETER_OPTIONS`` if defined,
        otherwise the default from ``PARAMETER_OPTION_DEFAULTS``.
    """
    PARAMETER_OPTION_DEFAULTS = {
        "indent": 0,
        "newline_if_set": False,
        "newline_indent": 0,
        "remove_line_if_empty": False,
    }

    PARAMETER_OPTIONS = {
        "PYPROJECT_PY_MODULES": {
            "indent": 8,
            "newline_if_set": True,
            "newline_indent": 4,
        },
        "PYPROJECT_DEPENDENCIES": {"indent": 8, "remove_line_if_empty": True},
    }

    default = PARAMETER_OPTION_DEFAULTS.get(option)
    if key not in PARAMETER_OPTIONS.keys():
        return default
    return PARAMETER_OPTIONS[key].get(option, default)


# Copied from scikit-ci/ci/utils.py
def indent(text, prefix, predicate=None):
    """Add *prefix* to the beginning of selected lines in *text*.

    Copied from ``textwrap.py`` (cpython/cpython@a2d2bef).

    Parameters
    ----------
    text : str
        The multiline string to indent.
    prefix : str
        String prepended to each selected line.
    predicate : callable, optional
        Called with each line; *prefix* is added only when it returns
        True.  Defaults to adding *prefix* to all non-blank lines.

    Returns
    -------
    str
        The indented text.
    """
    if predicate is None:

        def predicate(line):
            return line.strip()

    def prefixed_lines():
        for line in text.splitlines(True):
            yield prefix + line if predicate(line) else line

    return "".join(prefixed_lines())


def list_to_str(list_, newline=True):
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


def configure(template_file, parameters, output_file):
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
    with open(template_file) as file_:
        lines = file_.readlines()
        for line in lines:
            append = True
            for key in parameters.keys():
                value = str(parameters[key]).strip()
                if (
                    key in line
                    and not value
                    and parameter_option(key, "remove_line_if_empty")
                ):
                    append = False
                    break
                block_indent = " " * parameter_option(key, "indent")
                value = indent(value, block_indent)
                newline_indent = " " * parameter_option(key, "newline_indent")
                if value.strip() and parameter_option(key, "newline_if_set"):
                    value = f"\n{value}\n{newline_indent}"
                line = line.replace(f"@{key}@", value)
                # Windows paths need to have backslashes escaped preserved in writing of files
                line = line.replace("\\", "\\\\")
            if append:
                updated_lines.append(line)

    with open(output_file, "w") as file_:
        file_.writelines(updated_lines)


def from_group_to_wheel(group):
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
    base_params: dict,
    package_env_config: dict,
    SCRIPT_NAME: str,
    wheel_names: list,
    wheel_dependencies: dict,
):
    """Build a mapping of wheel name to ``pyproject.toml`` template parameters.

    This is a pure transformation and does not mutate global state.

    Parameters
    ----------
    base_params : dict
        Shared base parameters common to all wheels.
    package_env_config : dict
        Build environment configuration (ITK paths, versions, etc.).
    SCRIPT_NAME : str
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
    PYPROJECT_PY_PARAMETERS = {}
    for wheel_name in wheel_names:
        params = dict(base_params)

        # generator
        params["PYPROJECT_GENERATOR"] = f"python {SCRIPT_NAME} '{wheel_name}'"

        # name
        if wheel_name == "itk-meta":
            params["PYPROJECT_NAME"] = "itk"
            params["PYPROJECT_PLATLIB"] = r"false"
        else:
            params["PYPROJECT_NAME"] = wheel_name

        # long description
        if wheel_name == "itk-core":
            params["PYPROJECT_LONG_DESCRIPTION"] += (
                r"\n\n"
                "This package contain the toolkit framework used"
                " by other modules. There are common base classes for data objects and process"
                " objects, basic data structures such as Image, Mesh, QuadEdgeMesh, and"
                " SpatialObjects, and common functionality for operations such as finite"
                " differences, image adaptors, or image transforms."
            )
        elif wheel_name == "itk-filtering":
            params["PYPROJECT_LONG_DESCRIPTION"] += (
                r"\n\n"
                "These packages contains filters that modify data"
                " in the ITK pipeline framework.  These filters take an input object, such as an"
                " Image, and modify it to create an output.  Filters can be chained together to"
                " create a processing pipeline."
            )
        elif wheel_name == "itk-io":
            params["PYPROJECT_LONG_DESCRIPTION"] += (
                r"\n\n"
                "This package contains classes for reading and writing images and other data objects."
            )
        elif wheel_name == "itk-numerics":
            params["PYPROJECT_LONG_DESCRIPTION"] += (
                r"\n\n"
                "This package contains basic numerical tools and algorithms that"
                " have general applications outside of imaging."
            )
        elif wheel_name == "itk-registration":
            params["PYPROJECT_LONG_DESCRIPTION"] += (
                r"\n\n"
                "This package addresses the registration problem: "
                " find the spatial transformation between two images. This is a high"
                " level package that makes use of many lower level packages."
            )
        elif wheel_name == "itk-segmentation":
            params["PYPROJECT_LONG_DESCRIPTION"] += (
                r"\n\n"
                "This package addresses the segmentation problem: "
                " partition the image into classified regions (labels). This is a high"
                " level package that makes use of many lower level packages."
            )

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

        PYPROJECT_PY_PARAMETERS[wheel_name] = params

    return PYPROJECT_PY_PARAMETERS


def get_wheel_names(IPP_BuildWheelsSupport_DIR: str):
    """Read the ordered list of wheel names from ``WHEEL_NAMES.txt``.

    Parameters
    ----------
    IPP_BuildWheelsSupport_DIR : str
        Directory containing ``WHEEL_NAMES.txt``.

    Returns
    -------
    list[str]
        Stripped wheel names, one per line.
    """
    with open(os.path.join(IPP_BuildWheelsSupport_DIR, "WHEEL_NAMES.txt")) as _file:
        return [wheel_name.strip() for wheel_name in _file.readlines()]


def get_py_api():
    """Return the stable ABI tag for the running Python, or empty string.

    Returns
    -------
    str
        A tag like ``'cp311'`` for Python >= 3.11, or ``''`` otherwise.
    """
    # Return empty for Python < 3.11, otherwise a cp tag like 'cp311'
    if sys.version_info < (3, 11):
        return ""
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def get_wheel_dependencies(SCRIPT_DIR: str, version: str, wheel_names: list):
    """Parse ITK CMake files to build a wheel dependency graph.

    Parameters
    ----------
    SCRIPT_DIR : str
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
    regex_group_depends = r"set\s*\(\s*ITK\_GROUP\_([a-zA-Z0-9\_\-]+)\_DEPENDS\s*([a-zA-Z0-9\_\-\s]*)\s*"  # noqa: E501
    pattern = re.compile(regex_group_depends)
    with open(
        os.path.join(SCRIPT_DIR, "..", "cmake/ITKPythonPackage_BuildWheels.cmake")
    ) as file_:
        for line in file_.readlines():
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
    package_env_config: dict, SCRIPT_NAME: str, itk_package_version: str
):
    """Return the base ``pyproject.toml`` template parameters for ITK.

    Parameters
    ----------
    package_env_config : dict
        Build environment configuration.
    SCRIPT_NAME : str
        Name of the calling script.
    itk_package_version : str
        PEP 440 version string for the ITK packages.

    Returns
    -------
    dict[str, str]
        Base parameter mapping shared across all wheel configurations.
    """
    ITK_SOURCE_README: str = os.path.join(
        package_env_config["ITK_SOURCE_DIR"], "README.md"
    )
    return {
        "PYPROJECT_GENERATOR": f"python {SCRIPT_NAME} 'itk'",
        "PYPROJECT_NAME": r"itk",
        "PYPROJECT_VERSION": itk_package_version,
        "PYPROJECT_CMAKE_ARGS": r"",
        "PYPROJECT_PY_API": get_py_api(),
        "PYPROJECT_PLATLIB": r"true",
        "ITK_SOURCE_DIR": package_env_config["ITK_SOURCE_DIR"],
        "ITK_SOURCE_README": ITK_SOURCE_README,
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
        "PYPROJECT_DESCRIPTION": r"ITK is an open-source toolkit for multidimensional image analysis",  # noqa: E501
        "PYPROJECT_LONG_DESCRIPTION": r"ITK is an open-source, cross-platform library that "
        "provides developers with an extensive suite of software "
        "tools for image analysis. Developed through extreme "
        "programming methodologies, ITK employs leading-edge "
        "algorithms for registering and segmenting "
        "multidimensional scientific images.",
        "PYPROJECT_EXTRA_KEYWORDS": r'"scientific", "medical", "image", "imaging"',
        "PYPROJECT_DEPENDENCIES": r"",
    }


def main():
    # Parse arguments
    SCRIPT_DIR = os.path.dirname(__file__)
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="""CLI allowing to configure ``pyproject.toml`` found in the `` ITKPythonPackage ``
source tree.

Different versions of ``pyproject.toml`` can be generated based on the value
of the `wheel_name` positional parameter.

Usage::

    pyproject_configure.py [-h] [--output-dir OUTPUT_DIR] wheel_name

    positional arguments:
      wheel_name

    optional arguments:
      -h, --help   show this help message and exit
      --output-dir OUTPUT_DIR
                            Output directory for configured 'pyproject.toml'
                            (default: /work)

Accepted values for `wheel_name` are ``itk`` and all values read from
``WHEEL_NAMES.txt``.
""",
    )
    parser.add_argument("wheel_name")
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for configured 'pyproject.toml'",
        default=os.path.abspath(os.path.join(SCRIPT_DIR, "..")),
    )
    parser.add_argument(
        "--build-dir-root",
        type=str,
        default=f"{SCRIPT_DIR}/../",
        help="The root of the build resources.",
    )
    args = parser.parse_args()
    print(f"Reading configuration settings from {args.env_file}")
    package_env_config = read_env_file(args.env_file, args.build_dir_root)

    configure_one_pyproject_file(
        SCRIPT_DIR, package_env_config, args.output_dir, args.wheel_name
    )


def configure_one_pyproject_file(
    SCRIPT_DIR: str | bytes, package_env_config, output_dir, wheel_name: str = "itk"
):
    """Generate a configured ``pyproject.toml`` for a single wheel.

    Parameters
    ----------
    SCRIPT_DIR : str or bytes
        Path to the ``scripts/`` directory containing templates.
    package_env_config : dict
        Build environment configuration.
    output_dir : str or Path
        Directory where ``pyproject.toml`` will be written.
    wheel_name : str, optional
        Which wheel to configure (default ``'itk'``).
    """
    # Version needs to be python PEP 440 compliant (no leading v)
    PEP440_VERSION: str = package_env_config["ITK_PACKAGE_VERSION"].removeprefix("v")
    try:
        Version(
            PEP440_VERSION
        )  # Raise InvalidVersion exception if not PEP 440 compliant
    except ValueError:
        print(f"Invalid PEP 440 version: {PEP440_VERSION}")
        sys.exit(1)

    # Resolve script information locally

    IPP_BuildWheelsSupport_DIR = os.path.join(SCRIPT_DIR, "..", "BuildWheelsSupport")
    SCRIPT_NAME = os.path.basename(__file__)
    # Write itkVersion.py file to report ITK version in python.
    write_itkVersion_py(Path(output_dir) / "itkVersion.py", PEP440_VERSION)
    # Copy LICENSE file needed for each wheel
    shutil.copy(Path(IPP_BuildWheelsSupport_DIR) / "LICENSE", output_dir)

    base_params = build_base_pyproject_parameters(
        package_env_config, SCRIPT_NAME, PEP440_VERSION
    )

    wheel_names = get_wheel_names(IPP_BuildWheelsSupport_DIR)
    wheel_dependencies = get_wheel_dependencies(
        SCRIPT_DIR, base_params["PYPROJECT_VERSION"], wheel_names
    )

    PYPROJECT_PY_PARAMETERS = {"itk": dict(base_params)}
    PYPROJECT_PY_PARAMETERS.update(
        update_wheel_pyproject_toml_parameters(
            base_params,
            package_env_config,
            SCRIPT_NAME,
            wheel_names,
            wheel_dependencies,
        )
    )

    if wheel_name not in PYPROJECT_PY_PARAMETERS.keys():
        print(f"Unknown wheel name '{wheel_name}'")
        sys.exit(1)

    # Configure 'pyproject.toml'
    output_file = os.path.join(output_dir, "pyproject.toml")
    print(f"Generating: {output_file}")
    template = os.path.join(SCRIPT_DIR, "pyproject.toml.in")
    configure(template, PYPROJECT_PY_PARAMETERS[wheel_name], output_file)


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
    with open(filename, "w") as wfid:
        wfid.write(itk_version_python_code)


if __name__ == "__main__":
    main()
