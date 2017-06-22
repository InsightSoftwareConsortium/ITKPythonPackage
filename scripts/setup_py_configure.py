#!/usr/bin/env python

"""CLI allowing to configure ``setup.py`` found in ``ITKPythonPackage``
source tree.

Different version of ``setup.py`` can be generated based on the value
of the `wheel_name` positional parameter.

Usage::

    setup_py_configure.py [-h] [--output-dir OUTPUT_DIR] wheel_name

    positional arguments:
      wheel_name

    optional arguments:
      -h, --help            show this help message and exit
      --output-dir OUTPUT_DIR
                            Output directory for configured 'setup.py' script
                            (default: /work)


Accepted values for `wheel_name` are ``itk`` and all values read from
``WHEEL_NAMES.txt``.
"""

import argparse
import os
import re
import sys
import textwrap


PARAMETER_OPTION_DEFAULTS = {
    'indent': 0,
    'newline_if_set': False,
    'newline_indent': 0,
    'remove_line_if_empty': False
}

PARAMETER_OPTIONS = {
    'SETUP_PRE_CODE': {
        'remove_line_if_empty': True
    },
    'SETUP_PY_MODULES': {
        'indent': 8,
        'newline_if_set': True,
        'newline_indent': 4
    },
    'SETUP_INSTALL_REQUIRES': {
        'indent': 8,
        'remove_line_if_empty': True
    },
    'SETUP_POST_CODE': {
        'remove_line_if_empty': True
    }
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

    return ''.join(prefixed_lines())


def list_to_str(list_, newline=True):
    sep = ", "
    if newline:
        sep = ",\n"
    return sep.join(["'%s'" % item for item in list_])


def configure(template_file, parameters, output_file):
    """Configure `template_file` into `output_file` given a dictionary of
    `parameters`.
    """
    updated_lines = []
    with open(template_file, 'r') as file_:
        lines = file_.readlines()
        for line in lines:
            append = True
            for key in parameters.keys():
                value = parameters[key].strip()
                if (key in line
                        and not value
                        and parameter_option(key, 'remove_line_if_empty')):
                    append = False
                    break
                block_indent = " " * parameter_option(key, 'indent')
                value = indent(value, block_indent)
                newline_indent = " " * parameter_option(key, 'newline_indent')
                if value.strip() and parameter_option(key, 'newline_if_set'):
                    value = "\n%s\n%s" % (value, newline_indent)
                line = line.replace("@%s@" % key, value)
            if append:
                updated_lines.append(line)

    with open(output_file, 'w') as file_:
        file_.writelines(updated_lines)


def from_group_to_wheel(group):
    return "itk-%s" % group.lower()


def update_wheel_setup_py_parameters():
    global SETUP_PY_PARAMETERS
    for wheel_name in get_wheel_names():
        params = dict(ITK_SETUP_PY_PARAMETERS)

        # generator
        params['SETUP_GENERATOR'] = "python %s '%s'" % (SCRIPT_NAME, wheel_name)

        # name
        if wheel_name == 'itk-meta':
            params['SETUP_NAME'] = 'itk'
        else:
            params['SETUP_NAME'] = wheel_name


        # long description
        if wheel_name == 'itk-core':
            params['SETUP_LONG_DESCRIPTION'] += (r'\n\n'
            'This package contain the toolkit framework used'
            ' by other modules. There are common base classes for data objects and process'
            ' objects, basic data structures such as Image, Mesh, QuadEdgeMesh, and'
            ' SpatialObjects, and common functionality for operations such as finite'
            ' differences, image adaptors, or image transforms.')
        elif wheel_name == 'itk-filtering':
            params['SETUP_LONG_DESCRIPTION'] += (r'\n\n'
            'These packages contains filters that modify data'
            ' in the ITK pipeline framework.  These filters take an input object, such as an'
            ' Image, and modify it to create an output.  Filters can be chained together to'
            ' create a processing pipeline.')
        elif wheel_name == 'itk-io':
            params['SETUP_LONG_DESCRIPTION'] += (r'\n\n'
            'This package contains classes for reading and writing images and other data objects.')
        elif wheel_name == 'itk-numerics':
            params['SETUP_LONG_DESCRIPTION'] += (r'\n\n'
            'This package contains basic numerical tools and algorithms that'
            ' have general applications outside of imaging.')
        elif wheel_name == 'itk-registration':
            params['SETUP_LONG_DESCRIPTION'] += (r'\n\n'
            'This package addresses the registration problem: '
            ' find the spatial transformation between two images. This is a high'
            ' level package that makes use of many lower level packages.')
        elif wheel_name == 'itk-segmentation':
            params['SETUP_LONG_DESCRIPTION'] += (r'\n\n'
            'This package addresses the segmentation problem: '
            ' partition the image into classified regions (labels). This is a high'
            ' level package that makes use of many lower level packages.')

        # cmake_args
        params['SETUP_CMAKE_ARGS'] = list_to_str([
            '-DITKPythonPackage_WHEEL_NAME:STRING=%s' % wheel_name
        ])

        # py_modules
        if wheel_name != 'itk-core':
            params['SETUP_PY_MODULES'] = r''

        # install_requires
        wheel_depends = get_wheel_dependencies()[wheel_name]
        params['SETUP_INSTALL_REQUIRES'] = list_to_str(wheel_depends)

        SETUP_PY_PARAMETERS[wheel_name] = params


def get_wheel_names():
    with open(os.path.join(SCRIPT_DIR, 'WHEEL_NAMES.txt'), 'r') as _file:
        return [wheel_name.strip() for wheel_name in _file.readlines()]


def get_wheel_dependencies():
    """Return a dictionary of ITK wheel dependencies.
    """
    all_depends = {}
    regex_group_depends = \
        r'set\s*\(\s*ITK\_GROUP\_([a-zA-Z0-9\_\-]+)\_DEPENDS\s*([a-zA-Z0-9\_\-\s]*)\s*'  # noqa: E501
    pattern = re.compile(regex_group_depends)
    with open(os.path.join(SCRIPT_DIR, "..", "CMakeLists.txt"), 'r') as file_:
        for line in file_.readlines():
            match = re.search(pattern, line)
            if not match:
                continue
            wheel = from_group_to_wheel(match.group(1))
            _wheel_depends = [
                from_group_to_wheel(group)
                for group in match.group(2).split()
                ]
            all_depends[wheel] = _wheel_depends
    all_depends['itk-meta'] = [
        wheel_name for wheel_name in get_wheel_names()
        if wheel_name != 'itk-meta'
        ]
    all_depends['itk-meta'].append('numpy')
    return all_depends


SCRIPT_DIR = os.path.dirname(__file__)
SCRIPT_NAME = os.path.basename(__file__)

ITK_SETUP_PY_PARAMETERS = {
    'SETUP_GENERATOR': "python %s '%s'" % (SCRIPT_NAME, 'itk'),
    'SETUP_PRE_CODE': textwrap.dedent(
        r"""
        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
        from itkVersion import get_versions
        """
    ),
    'SETUP_NAME': r'itk',
    'SETUP_VERSION': r"""get_versions()['package-version']""",
    'SETUP_CMAKE_ARGS': r'',
    'SETUP_PY_MODULES': list_to_str([
        'itkBase',
        'itkConfig',
        'itkExtras',
        'itkLazy',
        'itkTemplate',
        'itkTypes',
        'itkVersion',
        'itkBuildOptions'
    ]),
    'SETUP_DOWNLOAD_URL': r'https://itk.org/ITK/resources/software.html',
    'SETUP_DESCRIPTION': r'ITK is an open-source toolkit for multidimensional image analysis',  # noqa: E501
    'SETUP_LONG_DESCRIPTION': r'ITK is an open-source, cross-platform library that '
                     'provides developers with an extensive suite of software '
                     'tools for image analysis. Developed through extreme '
                     'programming methodologies, ITK employs leading-edge '
                     'algorithms for registering and segmenting '
                     'multidimensional scientific images.',
    'SETUP_EXTRA_KEYWORDS': r'segmentation registration image imaging',
    'SETUP_INSTALL_REQUIRES': r'',
    'SETUP_POST_CODE': r''
}

SETUP_PY_PARAMETERS = {
    'itk': ITK_SETUP_PY_PARAMETERS
}

update_wheel_setup_py_parameters()


def main():

    # Defaults
    default_output_dir = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

    # Parse arguments
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument("wheel_name")
    parser.add_argument(
        "--output-dir", type=str,
        help="Output directory for configured 'setup.py' script",
        default=default_output_dir
        )
    args = parser.parse_args()
    template = os.path.join(SCRIPT_DIR, "setup.py.in")
    if args.wheel_name not in SETUP_PY_PARAMETERS.keys():
        print("Unknown wheel name '%s'" % args.wheel_name)
        sys.exit(1)

    # Configure 'setup.py'
    output_file = os.path.join(args.output_dir, 'setup.py')
    configure(template, SETUP_PY_PARAMETERS[args.wheel_name], output_file)

    # Configure or remove 'itk/__init__.py'
    init_py = os.path.join(args.output_dir, "itk", "__init__.py")
    if args.wheel_name in ["itk", "itk-core"]:
        with open(init_py, 'w') as file_:
            file_.write("# Stub required for setuptools\n")
    else:
        if os.path.exists(init_py):
            os.remove(init_py)

if __name__ == "__main__":
    main()
