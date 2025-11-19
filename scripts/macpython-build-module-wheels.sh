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

_script_dir=${_script_dir:=$(cd $(dirname $0) || exit 1; pwd)}
_ipp_dir=$(dirname ${_script_dir})
package_env_file=${_ipp_dir}/build/package.env
if [ ! -f "${package_env_file}" ]; then
  echo "MISSING: ${package_env_file}"
  echo "    RUN: ${_ipp_dir}/generate_build_environment.sh.sh"
  exit 1
fi
source "${package_env_file}"

if [[ -n ${ITK_MODULE_PREQ} ]]; then
  source "${_script_dir}/macpython-build-module-deps.sh"
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
# * SKBUILD_DIR
# * VENVS=()

MACPYTHON_PY_PREFIX=""
VENVS=()

source "${_script_dir}/macpython-build-common.sh"
# -----------------------------------------------------------------------

if test -e setup.py; then
  use_skbuild_classic=true
else
  use_skbuild_classic=false
fi


VENV="${VENVS[0]}"
Python3_EXECUTABLE=${VENV}/bin/python3
dot_clean ${VENV}
${Python3_EXECUTABLE} -m pip install --no-cache-dir delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel
# So delocate can find the libs
export DYLD_LIBRARY_PATH=${DYLD_LIBRARY_PATH}:${_ipp_dir}/oneTBB-prefix/lib

# Compile wheels re-using standalone project and archive cache
for VENV in "${VENVS[@]}"; do
    py_mm=$(basename ${VENV})
    Python3_EXECUTABLE=${VENV}/bin/python
    Python3_INCLUDE_DIR=$( find -L ${MACPYTHON_PY_PREFIX}/${py_mm}/include -name Python.h -exec dirname {} \; )

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"

    if $use_skbuild_classic; then
      # So older remote modules with setup.py continue to work
      ${Python3_EXECUTABLE} -m pip install --upgrade scikit-build
    fi

    if [[ $(arch) == "arm64" ]]; then
      plat_name="macosx-15.0-arm64"
      osx_target="15.0"
      osx_arch="arm64"
      build_path="${_ipp_dir}/ITK-${py_mm}-macosx_arm64"
    else
      plat_name="macosx-15.0-x86_64"
      osx_target="15.0"
      osx_arch="x86_64"
      build_path="${_ipp_dir}/ITK-${py_mm}-macosx_x86_64"
    fi
    if [[ ! -z "${MACOSX_DEPLOYMENT_TARGET}" ]]; then
      osx_target="${MACOSX_DEPLOYMENT_TARGET}"
    fi
    export MACOSX_DEPLOYMENT_TARGET=${osx_target}

    if [[ -e $PWD/requirements-dev.txt ]]; then
      ${Python3_EXECUTABLE} -m pip install --upgrade -r $PWD/requirements-dev.txt
    fi
    itk_build_path="${build_path}"
    if $use_skbuild_classic; then
      ${Python3_EXECUTABLE} setup.py bdist_wheel --build-type Release --plat-name ${plat_name} -G Ninja -- \
        -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
        -DITK_DIR:PATH=${itk_build_path} \
        -DCMAKE_INSTALL_LIBDIR:STRING=lib \
        -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
        -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${osx_target} \
        -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
        -DBUILD_TESTING:BOOL=OFF \
        -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        ${CMAKE_OPTIONS} \
      || exit 1
    else
      py_minor=$(echo $py_mm | cut -d '.' -f 2)
      wheel_py_api=""
      if test $py_minor -ge 11; then
        wheel_py_api=cp3$py_minor
      fi
      ${Python3_EXECUTABLE} -m build \
        --verbose \
        --wheel \
        --outdir dist \
        --no-isolation \
        --skip-dependency-check \
        --config-setting=cmake.define.CMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
        --config-setting=cmake.define.ITK_DIR:PATH=${itk_build_path} \
        --config-setting=cmake.define.CMAKE_INSTALL_LIBDIR:STRING=lib \
        --config-setting=cmake.define.WRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
        --config-setting=cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET:STRING=${osx_target} \
        --config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
        --config-setting=cmake.define.PY_SITE_PACKAGES_PATH:PATH="." \
        --config-setting=wheel.py-api=$wheel_py_api \
        --config-setting=cmake.define.BUILD_TESTING:BOOL=OFF \
        --config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        --config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        ${CMAKE_OPTIONS//'-D'/'--config-setting=cmake.define.'} \
      || exit 1
    fi
done

for wheel in $PWD/dist/*.whl; do
  ${DELOCATE_LISTDEPS} $wheel # lists library dependencies
  ${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
done
