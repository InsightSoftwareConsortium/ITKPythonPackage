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
# ENVIRONMENT VARIABLES
#
# These variables are set with the `export` bash command before calling the script.
# For example,
#
#   export DYLD_LIBRARY_PATH="/path/to/libs"
#   scripts/macpython-build-module-wheels.sh 3.7 3.9
#
# `DYLD_LIBRARY_PATH`: Shared libraries to be included in the resulting wheel.
#   For instance, `export DYLD_LIBRARY_PATH="/path/to/OpenCL.so:/path/to/OpenCL.so.1.2"`
#
# `ITK_MODULE_PREQ`: Prerequisite ITK modules that must be built before the requested module.
#   Format is `<org_name>/<module_name>@<module_tag>:<org_name>/<module_name>@<module_tag>:...`.
#   For instance, `export ITK_MODULE_PREQ=InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0`
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
      plat_name="macosx-15.0-arm64"
      osx_target="15.0"
      osx_arch="arm64"
      build_path="${SCRIPT_DIR}/../ITK-${py_mm}-macosx_arm64"
    else
      plat_name="macosx-15.0-x86_64"
      osx_target="15.0"
      osx_arch="x86_64"
      build_path="${SCRIPT_DIR}/../ITK-${py_mm}-macosx_x86_64"
    fi
    if [[ ! -z "${MACOSX_DEPLOYMENT_TARGET}" ]]; then
      osx_target="${MACOSX_DEPLOYMENT_TARGET}"
    fi
    export MACOSX_DEPLOYMENT_TARGET=${osx_target}

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
done

for wheel in ${_module_dir}/dist/*.whl; do
  ${DELOCATE_LISTDEPS} $wheel # lists library dependencies
  ${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
done
