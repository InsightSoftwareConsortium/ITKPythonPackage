#!/usr/bin/env bash

# Download and install Python.org's MacPython and install Pip

# Adapted from https://github.com/matthew-brett/multibuild
# osx_utils.sh
#The multibuild package, including all examples, code snippets and attached
#documentation is covered by the 2-clause BSD license.

    #Copyright (c) 2013-2016, Matt Terry and Matthew Brett; all rights
    #reserved.

    #Redistribution and use in source and binary forms, with or without
    #modification, are permitted provided that the following conditions are
    #met:

    #1. Redistributions of source code must retain the above copyright notice,
    #this list of conditions and the following disclaimer.

    #2. Redistributions in binary form must reproduce the above copyright
    #notice, this list of conditions and the following disclaimer in the
    #documentation and/or other materials provided with the distribution.

    #THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
    #IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
    #THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
    #PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
    #CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
    #EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
    #PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
    #PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
    #LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
    #NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
    #SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

set -x

MACPYTHON_URL=https://www.python.org/ftp/python
MACPYTHON_PY_PREFIX=/Library/Frameworks/Python.framework/Versions
GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py
DOWNLOADS_SDIR=downloads
WORKING_SDIR=working

# As of 2 November 2022 - latest Python of each version with binary download
# available.
# See: https://www.python.org/downloads/mac-osx/
LATEST_2p7=2.7.18
LATEST_3p5=3.5.4
LATEST_3p6=3.6.8
LATEST_3p7=3.7.9
LATEST_3p8=3.8.10
LATEST_3p9=3.9.13
LATEST_3p10=3.10.11
LATEST_3p11=3.11.4
LATEST_3p12=3.12.0


function check_python {
    if [ -z "$PYTHON_EXE" ]; then
        echo "PYTHON_EXE variable not defined"
        exit 1
    fi
}

function check_pip {
    if [ -z "$PIP_CMD" ]; then
        echo "PIP_CMD variable not defined"
        exit 1
    fi
}

function check_var {
    if [ -z "$1" ]; then
        echo "required variable not defined"
        exit 1
    fi
}

function get_py_digit {
    check_python
    $PYTHON_EXE -c "import sys; print(sys.version_info[0])"
}

function get_py_mm {
    check_python
    $PYTHON_EXE -c "import sys; print('{0}.{1}'.format(*sys.version_info[0:2]))"
}

function get_py_mm_nodot {
    check_python
    $PYTHON_EXE -c "import sys; print('{0}{1}'.format(*sys.version_info[0:2]))"
}

function get_py_prefix {
    check_python
    $PYTHON_EXE -c "import sys; print(sys.prefix)"
}

function fill_pyver {
    # Convert major or major.minor format to major.minor.micro
    #
    # Hence:
    # 2 -> 2.7.11  (depending on LATEST_2p7 value)
    # 2.7 -> 2.7.11  (depending on LATEST_2p7 value)
    local ver=$1
    check_var $ver
    if [[ $ver =~ [0-9]+\.[0-9]+\.[0-9]+ ]]; then
        # Major.minor.micro format already
        echo $ver
    elif [ $ver == 2 ] || [ $ver == "2.7" ]; then
        echo $LATEST_2p7
    elif [ $ver == 3 ] || [ $ver == "3.11" ]; then
        echo $LATEST_3p11
    elif [ $ver == "3.12" ]; then
        echo $LATEST_3p12
    elif [ $ver == "3.10" ]; then
        echo $LATEST_3p10
    elif [ $ver == "3.9" ]; then
        echo $LATEST_3p9
    elif [ $ver == "3.8" ]; then
        echo $LATEST_3p8
    elif [ $ver == "3.7" ]; then
        echo $LATEST_3p7
    elif [ $ver == "3.6" ]; then
        echo $LATEST_3p6
    elif [ $ver == "3.5" ]; then
        echo $LATEST_3p5
    else
        echo "Can't fill version $ver" 1>&2
        exit 1
    fi
}

function macpython_sdk_list_for_version {
    # return a list of SDK targets supported for a given CPython version
    # Parameters
    #   $py_version (python version in major.minor.extra format)
    # eg
    #  macpython_sdks_for_version 2.7.15
    #  >> 10.6 10.9
    local _ver=$(fill_pyver $1)
    local _major=${_ver%%.*}
    local _return

    if [ "${PLAT}" = "arm64" ]; then
        _return="11.0"
    elif [ "$_major" -eq "2" ]; then
        [ $(lex_ver $_ver) -lt $(lex_ver 2.7.18) ] && _return="10.6"
        [ $(lex_ver $_ver) -ge $(lex_ver 2.7.15) ] && _return="$_return 10.9"
    elif [ "$_major" -eq "3" ]; then
        [ $(lex_ver $_ver) -lt $(lex_ver 3.8)    ] && _return="10.6"
        [ $(lex_ver $_ver) -ge $(lex_ver 3.6.5)  ] && _return="$_return 10.9"
    else
        echo "Error version=${_ver}, expecting 2.x or 3.x" 1>&2
        exit 1
    fi
    echo $_return
}

function macpython_sdk_for_version {
    # assumes the output of macpython_sdk_list_for_version is a list
    # of SDK versions XX.Y in sorted order, eg "10.6 10.9" or "10.9"
    echo $(macpython_sdk_list_for_version $1) | awk -F' ' '{print $NF}'
}

function pyinst_ext_for_version {
    # echo "pkg" or "dmg" depending on the passed Python version
    # Parameters
    #   $py_version (python version in major.minor.extra format)
    #
    # Earlier Python installers are .dmg, later are .pkg.
    local py_version=$1
    check_var $py_version
    py_version=$(fill_pyver $py_version)
    local py_0=${py_version:0:1}
    if [ $py_0 -eq 2 ]; then
        if [ "$(lex_ver $py_version)" -ge "$(lex_ver 2.7.9)" ]; then
            echo "pkg"
        else
            echo "dmg"
        fi
    elif [ $py_0 -ge 3 ]; then
		echo "pkg"
    fi
}

function pyinst_fname_for_version {
    # echo filename for OSX installer file given Python and minimum
    # macOS versions
    # Parameters
    #   $py_version (Python version in major.minor.extra format)
    #   $py_osx_ver: {major.minor | not defined}
    #       if defined, the minimum macOS SDK version that Python is
    #       built for, eg: "10.6" or "10.9", if not defined, infers
    #       this from $py_version using macpython_sdk_for_version
    local py_version=$1
    local py_osx_ver=${2:-$(macpython_sdk_for_version $py_version)}
    local inst_ext=$(pyinst_ext_for_version $py_version)
    if [ "${PLAT:-}" == "arm64" ] || [ "${PLAT:-}" == "universal2" ]; then
      if [ "$py_version" == "3.9.1" ]; then
        echo "python-${py_version}-macos11.0.${inst_ext}"
      else
        echo "python-${py_version}-macos11.${inst_ext}"
      fi
    else
      if [ "$py_version" == "3.7.9" ]; then
        echo "python-${py_version}-macosx${py_osx_ver}.${inst_ext}"
      else
        echo "python-${py_version}-macos${py_osx_ver}.${inst_ext}"
      fi
    fi
}

function get_macpython_arch {
    # echo arch (e.g. intel or x86_64), extracted from the distutils platform tag
    # Parameters
    #   $distutils_plat   PEP425 style platform tag, or if not provided, calls
    #                       the function get_distutils_platform, provided by
    #                       common_utils.sh. Fails if this is not a mac platform
    #
    # Note: MUST only be called after the version of Python used to build the
    # target wheel has been installed and is on the path
    local distutils_plat=${1:-$(get_distutils_platform)}
    if [[ $distutils_plat =~ macosx-(1[0-9]\.[0-9]+)-(.*) ]]; then
        echo ${BASH_REMATCH[2]}
    else
        echo "Error parsing macOS distutils platform '$distutils_plat'"
        exit 1
    fi
}

function get_macpython_osx_ver {
    # echo minimum macOS version (e.g. 10.9) from the distutils platform tag
    # Parameters
    #   $distutils_plat   PEP425 style platform tag, or if not provided, calls
    #                       the function get_distutils_platform, provided by
    #                       common_utils.sh. Fails if this is not a mac platform
    #
    # Note: MUST only be called after the version of Python used to build the
    # target wheel has been installed and is on the path
    local distutils_plat=${1:-$(get_distutils_platform)}
    if [[ $distutils_plat =~ macosx-(1[0-9]\.[0-9]+)-(.*) ]]; then
        echo ${BASH_REMATCH[1]}
    else
        echo "Error parsing macOS distutils platform '$distutils_plat'"
        exit 1
    fi
}

function macpython_impl_for_version {
    # echo Python implementation (cp for CPython, pp for PyPy) given a
    # suitably formatted version string
    # Parameters:
    #     $version : [implementation-]major[.minor[.patch]]
    #         Python implementation, e.g. "3.6" for CPython or
    #         "pypy-5.4" for PyPy
    local version=$1
    check_var $1
    if [[ "$version" =~ ^pypy ]]; then
        echo pp
    elif [[ "$version" =~ ([0-9\.]+) ]]; then
        echo cp
    else
        echo "config error: Issue parsing this implementation in install_python:"
        echo "    version=$version"
        exit 1
    fi
}

function strip_macpython_ver_prefix {
    # strip any implementation prefix from a Python version string
    # Parameters:
    #     $version : [implementation-]major[.minor[.patch]]
    #         Python implementation, e.g. "3.6" for CPython or
    #         "pypy-5.4" for PyPy
    local version=$1
    check_var $1
    if [[ "$version" =~ (pypy-)?([0-9\.]+) ]]; then
        echo ${BASH_REMATCH[2]}
    fi
}

function install_macpython {
    # Install Python and set $PYTHON_EXE to the installed executable
    # Parameters:
    #     $version : [implementation-]major[.minor[.patch]]
    #         The Python implementation to install, e.g. "3.6", "pypy-5.4" or "pypy3.6-7.2"
    #     $py_osx_ver: {major.minor | not defined}
    #       if defined, the macOS version that CPython is built for, e.g.
    #       "10.6" or "10.9". Ignored for PyPy
    local version=$1
    local py_osx_ver=$2
    local impl=$(macpython_impl_for_version $version)
    if [[ "$impl" == "pp" ]]; then
        install_pypy $version
    elif [[ "$impl" == "cp" ]]; then
        local stripped_ver=$(strip_macpython_ver_prefix $version)
        install_mac_cpython $stripped_ver $py_osx_ver
    else
        echo "Unexpected Python impl: ${impl}"
        exit 1
    fi
}

function install_mac_cpython {
    # Installs Python.org Python
    # Parameters
    #   $py_version
    #       Version given in major or major.minor or major.minor.micro e.g
    #       "3" or "3.7" or "3.7.1".
    #   $py_osx_ver
    #       {major.minor | not defined}
    #       if defined, the macOS version that Python is built for, e.g.
    #        "10.6" or "10.9"
    # sets $PYTHON_EXE variable to Python executable
    local py_version=$(fill_pyver $1)
    local py_osx_ver=$2
    #local py_stripped=$(strip_ver_suffix $py_version)
    local py_stripped=$py_version
    local py_inst=$(pyinst_fname_for_version $py_version $py_osx_ver)
    local inst_path=$DOWNLOADS_SDIR/$py_inst
    local retval=""
    mkdir -p $DOWNLOADS_SDIR
    # exit early on curl errors, but don't let it exit the shell
    curl -f $MACPYTHON_URL/$py_stripped/${py_inst} > $inst_path || retval=$?
    if [ ${retval:-0} -ne 0 ]; then
      echo "Python download failed! Check ${py_inst} exists on the server."
      exit $retval
    fi

    if [ "${py_inst: -3}" == "dmg" ]; then
        hdiutil attach $inst_path -mountpoint /Volumes/Python
        inst_path=/Volumes/Python/Python.mpkg
    fi
    sudo installer -pkg $inst_path -target /
    local py_mm=${py_version%.*}
    PYTHON_EXE=$MACPYTHON_PY_PREFIX/$py_mm/bin/python$py_mm
    # Install certificates for Python 3.6
    local inst_cmd="/Applications/Python ${py_mm}/Install Certificates.command"
    if [ -e "$inst_cmd" ]; then
        sh "$inst_cmd"
    fi
    PIP_CMD="$MACPYTHON_PY_PREFIX/$py_mm/bin/python$py_mm -m pip"
    $PIP_CMD install --upgrade pip
    export PIP_CMD
}

function install_virtualenv {
    # Generic install of virtualenv
    # Installs virtualenv into python given by $PYTHON_EXE
    # Assumes virtualenv will be installed into same directory as $PYTHON_EXE
    check_pip
    # Travis VMS install virtualenv for system python by default - force
    # install even if installed already
    $PIP_CMD install virtualenv --ignore-installed
    check_python
    VIRTUALENV_CMD="$(dirname $PYTHON_EXE)/virtualenv"
    export VIRTUALENV_CMD
}

function make_workon_venv {
    # Make a virtualenv in given directory ('venv' default)
    # Set $PYTHON_EXE, $PIP_CMD to virtualenv versions
    # Parameter $venv_dir
    #    directory for virtualenv
    local venv_dir=$1
    if [ -z "$venv_dir" ]; then
        venv_dir="venv"
    fi
    venv_dir=`abspath $venv_dir`
    check_python
    $PYTHON_EXE -m virtualenv $venv_dir
    PYTHON_EXE=$venv_dir/bin/python
    PIP_CMD=$venv_dir/bin/pip
}

# Remove previous versions
#echo "Remove and update Python files at ${MACPYTHON_FRAMEWORK}"
#sudo rm -rf ${MACPYTHON_FRAMEWORK}

if test "$(arch)" == "arm64"; then
  echo "we are arm"
  PLAT=arm64
  for pyversion in $LATEST_3p9 $LATEST_3p10 $LATEST_3p11; do
    install_macpython $pyversion 11
    install_virtualenv
  done
else
  # Deployment target requirements:
  # * 10.9: Python 3.7
  # * 11: Python >= 3.8
  for pyversion in $LATEST_3p9 $LATEST_3p10 $LATEST_3p11; do
    install_macpython $pyversion 11
    install_virtualenv
  done
fi
