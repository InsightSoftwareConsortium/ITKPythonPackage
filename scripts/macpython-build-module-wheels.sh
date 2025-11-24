#!/usr/bin/env bash

########################################################################
# Run this script in an ITK external module directory to build the
# Python wheel packages for macOS for an ITK external module.
#
# ========================================================================
# PARAMETERS
#
# Versions can be restricted by passing them in as arguments to the script.
# For example,
#
#   scripts/macpython-build-module-wheels.sh 3.7 3.9
# Shared libraries can be included in the wheel by exporting them to DYLD_LIBRARY_PATH before
# running this script.
#
# ===========================================
# ENVIRONMENT VARIABLES: DYLD_LIBRARY_PATH
#
# These variables are set in build/package.env before calling this script.
# For example,
#   generate_build_environment.sh # creates default build/package.env
#   edit build/package.env with desired build elements
#   scripts/macpython-build-module-wheels.sh 3.9
#
########################################################################


# -----------------------------------------------------------------------
# (Optional) Build ITK module dependencies

script_dir=$(cd $(dirname $0) || exit 1; pwd)

if [[ -n ${ITK_MODULE_PREQ} ]]; then
  source "${script_dir}/macpython-build-module-deps.sh"
fi

# -----------------------------------------------------------------------
# These variables are set in common script:
#
# * CMAKE_EXECUTABLE
# * CMAKE_OPTIONS
# * MACPYTHON_PY_PREFIX
# * PYBINARIES
# * PYTHON_VERSIONS
# * NINJA_EXECUTABLE
# * SCRIPT_DIR
# * SKBUILD_DIR
# * VENVS=()

MACPYTHON_PY_PREFIX=""
SCRIPT_DIR=""
VENVS=()

source "${script_dir}/macpython-build-common.sh"
# -----------------------------------------------------------------------

VENV="${VENVS[0]}"
Python3_EXECUTABLE=${VENV}/bin/python3
dot_clean ${VENV}
${Python3_EXECUTABLE} -m pip install --no-cache-dir delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel
export DYLD_LIBRARY_PATH=${DYLD_LIBRARY_PATH}:${script_dir}/../oneTBB-prefix/lib

_module_dir="$(pwd -P)"

# Compile wheels re-using standalone project and archive cache
for VENV in "${VENVS[@]}"; do
    py_mm=$(basename ${VENV})
    Python3_EXECUTABLE=${VENV}/bin/python
    Python3_INCLUDE_DIR=$( find -L ${MACPYTHON_PY_PREFIX}/${py_mm}/include -name Python.h -exec dirname {} \; )

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"

    if [[ $(arch) == "arm64" ]]; then
      osx_arch="arm64"
    else
      osx_arch="x86_64"
    fi
    if [[ -z "${MACOSX_DEPLOYMENT_TARGET}" ]]; then
      MACOSX_DEPLOYMENT_TARGET=15.0
    else
      MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET}"
    fi
    export MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET}
    build_path="${_ipp_dir}/ITK-${py_mm}-macosx_${osx_arch}"
    plat_name="macosx-${MACOSX_DEPLOYMENT_TARGET}-${osx_arch}"

    if [[ -e $PWD/requirements-dev.txt ]]; then
      ${Python3_EXECUTABLE} -m pip install --upgrade -r $PWD/requirements-dev.txt
    fi
    itk_build_path="${build_path}"
    py_minor=$(echo $py_mm | cut -d '.' -f 2)
    wheel_py_api=""
    if test $py_minor -ge 11; then
      wheel_py_api=cp3$py_minor
    fi
    ${Python3_EXECUTABLE} -m build \
      --verbose \
      --wheel \
      --outdir ${_module_dir}/dist \
      --no-isolation \
      --skip-dependency-check \
      --config-setting=cmake.define.CMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
      --config-setting=cmake.define.ITK_DIR:PATH=${itk_build_path} \
      --config-setting=cmake.define.CMAKE_INSTALL_LIBDIR:STRING=lib \
      --config-setting=cmake.define.WRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
      --config-setting=cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
      --config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
      --config-setting=cmake.define.CMAKE_CXX_COMPILER:STRING=${CXX} \
      --config-setting=cmake.define.CMAKE_C_COMPILER:STRING=${CC} \
      --config-setting=cmake.define.PY_SITE_PACKAGES_PATH:PATH="." \
      --config-setting=wheel.py-api=$wheel_py_api \
      --config-setting=cmake.define.BUILD_TESTING:BOOL=OFF \
      --config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
      --config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
      ${CMAKE_OPTIONS//'-D'/'--config-setting=cmake.define.'} \
    || exit 1
done

for wheel in ${_module_dir}/dist/*.whl; do
  ${DELOCATE_LISTDEPS} $wheel # lists library dependencies
  ${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
done
