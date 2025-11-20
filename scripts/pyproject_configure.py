#!/usr/bin/env python

"""CLI allowing to configure ``pyproject.toml`` found in ``ITKPythonPackage``
source tree.

Different version of ``pyproject.toml`` can be generated based on the value
of the `wheel_name` positional parameter.

Usage::

    pyproject_configure.py [-h] [--output-dir OUTPUT_DIR] wheel_name

    positional arguments:
      wheel_name

    optional arguments:
      -h, --help            show this help message and exit
      --output-dir OUTPUT_DIR
                            Output directory for configured 'pyproject.toml'
                            (default: /work)


Accepted values for `wheel_name` are ``itk`` and all values read from
``WHEEL_NAMES.txt``.
"""

import argparse
import os
import re
import sys
import textwrap

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PARAMETER_OPTION_DEFAULTS = {
    "indent": 0,
    "newline_if_set": False,
    "newline_indent": 0,
    "remove_line_if_empty": False,
}

PARAMETER_OPTIONS = {
    "PYPROJECT_PY_MODULES": {"indent": 8, "newline_if_set": True, "newline_indent": 4},
    "PYPROJECT_DEPENDENCIES": {"indent": 8, "remove_line_if_empty": True},
}


def parameter_option(key, option):
    """Return value of `option` associated with parameter `key`.

    If no option is found in `PARAMETER_OPTIONS`, default value from
    `PARAMETER_OPTION_DEFAULTS` is returned.
    """
    default = PARAMETER_OPTION_DEFAULTS.get(option)
    if key not in PARAMETER_OPTIONS.keys():
        return default
    return PARAMETER_OPTIONS[key].get(option, default)


# Copied from scikit-ci/ci/utils.py
def indent(text, prefix, predicate=None):
    """Adds 'prefix' to the beginning of selected lines in 'text'.
    If 'predicate' is provided, 'prefix' will only be added to the lines
    where 'predicate(line)' is True. If 'predicate' is not provided,
    it will default to adding 'prefix' to all non-empty lines that do not
    consist solely of whitespace characters.

    Copied from textwrap.py available in python 3 (cpython/cpython@a2d2bef)
    """
    if predicate is None:

        def predicate(line):
            return line.strip()

    def prefixed_lines():
        for line in text.splitlines(True):
            yield (prefix + line if predicate(line) else line)

    return "".join(prefixed_lines())


def list_to_str(list_, newline=True):
    sep = ", "
    if newline:
        sep = ",\n"
    return sep.join(['"%s"' % item for item in list_])


def configure(template_file, parameters, output_file):
    """Configure `template_file` into `output_file` given a dictionary of
    `parameters`.
    """
    updated_lines = []
    with open(template_file, "r") as file_:
        lines = file_.readlines()
        for line in lines:
            append = True
            for key in parameters.keys():
                value = parameters[key].strip()
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
                    value = "\n%s\n%s" % (value, newline_indent)
                line = line.replace("@%s@" % key, value)
            if append:
                updated_lines.append(line)

    with open(output_file, "w") as file_:
        file_.writelines(updated_lines)


def from_group_to_wheel(group):
    return "itk-%s" % group.lower()


def update_wheel_pyproject_toml_parameters():
    global PYPROJECT_PY_PARAMETERS
    for wheel_name in get_wheel_names():
        params = dict(ITK_PYPROJECT_PY_PARAMETERS)

        # generator
        params["PYPROJECT_GENERATOR"] = "python %s '%s'" % (SCRIPT_NAME, wheel_name)

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
                "-DITK_WRAP_unsigned_short:BOOL=ON",
                "-DITK_WRAP_double:BOOL=ON",
                "-DITK_WRAP_complex_double:BOOL=ON",
                "-DITK_WRAP_IMAGE_DIMS:STRING=2;3;4",
                "-DITK_WRAP_DOC:BOOL=ON",
                "-DITKPythonPackage_WHEEL_NAME:STRING=%s" % wheel_name,
            ],
            True,
        )

        # install_requires
        wheel_depends = get_wheel_dependencies()[wheel_name]

        # py_modules
        if wheel_name != "itk-core":
            params["PYPROJECT_PY_MODULES"] = r""
        else:
            wheel_depends.append("numpy")

        params["PYPROJECT_DEPENDENCIES"] = list_to_str(wheel_depends)

        PYPROJECT_PY_PARAMETERS[wheel_name] = params


def get_wheel_names():
    with open(os.path.join(SCRIPT_DIR, "WHEEL_NAMES.txt"), "r") as _file:
        return [wheel_name.strip() for wheel_name in _file.readlines()]


def get_version():
    from itkVersion import get_versions

    version = get_versions()["package-version"]
    return version


def get_py_api():
    import sys

    if sys.version_info < (3, 11):
        return ""
    else:
        return "cp" + str(sys.version_info.major) + str(sys.version_info.minor)


def get_wheel_dependencies():
    """Return a dictionary of ITK wheel dependencies."""
    all_depends = {}
    regex_group_depends = r"set\s*\(\s*ITK\_GROUP\_([a-zA-Z0-9\_\-]+)\_DEPENDS\s*([a-zA-Z0-9\_\-\s]*)\s*"  # noqa: E501
    pattern = re.compile(regex_group_depends)
    version = get_version()
    with open(os.path.join(SCRIPT_DIR, "..", "CMakeLists.txt"), "r") as file_:
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
        for wheel_name in get_wheel_names()
        if wheel_name != "itk-meta"
    ]
    all_depends["itk-meta"].append("numpy")
    return all_depends


SCRIPT_DIR = os.path.dirname(__file__)
SCRIPT_NAME = os.path.basename(__file__)

ITK_PYPROJECT_PY_PARAMETERS = {
    "PYPROJECT_GENERATOR": "python %s '%s'" % (SCRIPT_NAME, "itk"),
    "PYPROJECT_NAME": r"itk",
    "PYPROJECT_VERSION": get_version(),
    "PYPROJECT_CMAKE_ARGS": r"",
    "PYPROJECT_PY_API": get_py_api(),
    "PYPROJECT_PLATLIB": r"true",
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

PYPROJECT_PY_PARAMETERS = {"itk": ITK_PYPROJECT_PY_PARAMETERS}

update_wheel_pyproject_toml_parameters()


def main():
    # Defaults
    default_output_dir = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

    # Parse arguments
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("wheel_name")
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for configured 'pyproject.toml'",
        default=default_output_dir,
    )
    args = parser.parse_args()
    template = os.path.join(SCRIPT_DIR, "pyproject.toml.in")
    if args.wheel_name not in PYPROJECT_PY_PARAMETERS.keys():
        print("Unknown wheel name '%s'" % args.wheel_name)
        sys.exit(1)

    # Configure 'pyproject.toml'
    output_file = os.path.join(args.output_dir, "pyproject.toml")
    configure(template, PYPROJECT_PY_PARAMETERS[args.wheel_name], output_file)

    # Configure or remove 'itk/__init__.py'
    # init_py = os.path.join(args.output_dir, "itk", "__init__.py")
    # if args.wheel_name in ["itk", "itk-core"]:
    # with open(init_py, 'w') as file_:
    # file_.write("# Stub required for package\n")
    # else:
    # if os.path.exists(init_py):
    # os.remove(init_py)


if __name__ == "__main__":
    main()
