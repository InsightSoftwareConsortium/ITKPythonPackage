#!/usr/bin/env bash

# Run this script inside a dockcross container to build Python wheels for an ITK module.
#
# Versions can be restricted by passing them in as arguments to the script.
# For example,
#
#   /tmp/dockcross-manylinux-x64 manylinux-build-module-wheels.sh cp39
#
# Shared library dependencies can be included in the wheel by mounting them to /usr/lib64 or /usr/local/lib64 
# before running this script.
# 
# For example,
#
#   DOCKER_ARGS="-v /path/to/lib.so:/usr/local/lib64/lib.so"
#   /tmp/dockcross-manylinux-x64 -a "$DOCKER_ARGS" manylinux-build-module-wheels.sh
#
# The specialized manylinux container version should be set prior to running this script.
# See https://github.com/dockcross/dockcross for available versions and tags.
#
# For example, `docker run -e <var>` can be used to set an environment variable when launching a container:
#
#   export MANYLINUX_VERSION=2014
#   docker run --rm dockcross/manylinux${MANYLINUX_VERSION}-x64:${IMAGE_TAG} > /tmp/dockcross-manylinux-x64
#   chmod u+x /tmp/dockcross-manylinux-x64
#   /tmp/dockcross-manylinux-x64 -e MANYLINUX_VERSION manylinux-build-module-wheels.sh cp39
#

# -----------------------------------------------------------------------
# Script argument parsing
#
usage()
{
  echo "Usage:
  manylinux-build-module-wheels
    [ -h | --help ]           show usage
    [ -c | --cmake_options ]  space-separated string of CMake options to forward to the module (e.g. \"--config-setting=cmake.define.BUILD_TESTING=OFF\")
    [ -x | --exclude_libs ]   semicolon-separated library names to exclude when repairing wheel (e.g. \"libcuda.so\")
    [ python_version ]        build wheel for a specific python version. (e.g. cp39)"
  exit 2
}

PARSED_ARGS=$(getopt -a -n dockcross-manylinux-download-cache-and-build-module-wheels \
  -o hc:x: --long help,cmake_options:,exclude_libs: -- "$@")
eval set -- "$PARSED_ARGS"

while :
do
  case "$1" in
    -h | --help) usage; break ;;
    -c | --cmake_options) CMAKE_OPTIONS="$2" ; shift 2 ;;
    -x | --exclude_libs) EXCLUDE_LIBS="$2" ; shift 2 ;;
    --) shift; break ;;
    *) echo "Unexpected option: $1.";
       usage; break ;;
  esac
done

PYTHON_VERSION="$@"
# -----------------------------------------------------------------------

# -----------------------------------------------------------------------
# These variables are set in common script:
#
ARCH=""
PYBINARIES=""

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/manylinux-build-common.sh"
# -----------------------------------------------------------------------

# Set up library paths in container so that shared libraries can be added to wheels
sudo ldconfig
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/work/oneTBB-prefix/lib:/usr/lib:/usr/lib64:/usr/local/lib:/usr/local/lib64

if test -e setup.py; then
  use_skbuild_classic=true
else
  use_skbuild_classic=false
fi

# Compile wheels re-using standalone project and archive cache
for PYBIN in "${PYBINARIES[@]}"; do
    Python3_EXECUTABLE=${PYBIN}/python
    Python3_INCLUDE_DIR=$( find -L ${PYBIN}/../include/ -name Python.h -exec dirname {} \; )

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"

    if $use_skbuild_classic; then
      # So older remote modules with setup.py continue to work
      ${Python3_EXECUTABLE} -m pip install --upgrade scikit-build
    fi

    if [[ -e /work/requirements-dev.txt ]]; then
      ${PYBIN}/pip install --upgrade -r /work/requirements-dev.txt
    fi
    if [[ -e /ITKPythonPackage/requirements-dev.txt ]]; then
      ${PYBIN}/pip install --upgrade -r /ITKPythonPackage/requirements-dev.txt
    fi
    version=$(basename $(dirname ${PYBIN}))
    # Remove "m" -- not present in Python 3.8 and later
    version=${version:0:9}
    itk_build_dir=/work/$(basename /ITKPythonPackage/ITK-${version}*-manylinux${MANYLINUX_VERSION}_${ARCH})
    ln -fs /ITKPythonPackage/ITK-${version}*-manylinux${MANYLINUX_VERSION}_${ARCH} $itk_build_dir
    if [[ ! -d ${itk_build_dir} ]]; then
      echo 'ITK build tree not available!' 1>&2
      exit 1
    fi
    itk_source_dir=/work/ITK-source/ITK
    ln -fs /ITKPythonPackage/ITK-source/ /work/ITK-source
    if [[ ! -d ${itk_source_dir} ]]; then
      echo 'ITK source tree not available!' 1>&2
      exit 1
    fi
    if $use_skbuild_classic; then
      ${PYBIN}/python setup.py clean
      ${PYBIN}/python setup.py bdist_wheel --build-type Release -G Ninja -- \
        -DITK_DIR:PATH=${itk_build_dir} \
        -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
        -DCMAKE_CXX_COMPILER_TARGET:STRING=$(uname -m)-linux-gnu \
        -DCMAKE_INSTALL_LIBDIR:STRING=lib \
        -DBUILD_TESTING:BOOL=OFF \
        -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        ${CMAKE_OPTIONS} \
      || exit 1
    else
      py_minor=$(echo $version | cut -d '-' -f 1 | cut -d '3' -f 2)
      wheel_py_api=""
      if test $py_minor -ge 11; then
        wheel_py_api=cp3$py_minor
      fi
      ${PYBIN}/python -m build \
        --verbose \
        --wheel \
        --outdir dist \
        --no-isolation \
        --skip-dependency-check \
        --config-setting=cmake.define.ITK_DIR:PATH=${itk_build_dir} \
        --config-setting=cmake.define.WRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
        --config-setting=cmake.define.CMAKE_CXX_COMPILER_TARGET:STRING=$(uname -m)-linux-gnu \
        --config-setting=cmake.define.CMAKE_INSTALL_LIBDIR:STRING=lib \
        --config-setting=cmake.define.PY_SITE_PACKAGES_PATH:PATH="." \
        --config-setting=wheel.py-api=$wheel_py_api \
        --config-setting=cmake.define.BUILD_TESTING:BOOL=OFF \
        --config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        --config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        ${CMAKE_OPTIONS//'-D'/'--config-setting=cmake.define.'} \
      || exit 1
    fi
done

# Convert list of excluded libs in --exclude_libs to auditwheel --exclude options
if test -n "$EXCLUDE_LIBS"; then
  AUDITWHEEL_EXCLUDE_ARGS="--exclude ${EXCLUDE_LIBS//;/ --exclude }"
fi

sudo ${Python3_EXECUTABLE} -m pip install auditwheel
for whl in dist/*linux*$(uname -m).whl; do
  auditwheel repair ${whl} -w /work/dist/ ${AUDITWHEEL_EXCLUDE_ARGS} 
  if $use_skbuild_classic; then
    rm ${whl}
  fi
done

if compgen -G "dist/itk*-linux*.whl" > /dev/null; then
  for itk_wheel in dist/itk*-linux*.whl; do
    rm ${itk_wheel}
  done
fi
