#!/usr/bin/env bash

# Run this script to build the Python wheel packages for macOS for an ITK
# external module.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/macpython-build-module-wheels.sh 2.7 3.5
#
# Shared libraries can be included in the wheel by exporting them to DYLD_LIBRARY_PATH before
# running this script.
# 
# For example,
#
#   export DYLD_LIBRARY_PATH="/path/to/libs"
#   scripts/macpython-build-module-wheels.sh cp39
#

# -----------------------------------------------------------------------
# These variables are set in common script:
#
MACPYTHON_PY_PREFIX=""
# PYBINARIES="" # unused
SCRIPT_DIR=""
VENVS=()

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/macpython-build-common.sh"
# -----------------------------------------------------------------------

VENV="${VENVS[0]}"
Python3_EXECUTABLE=${VENV}/bin/python3
${Python3_EXECUTABLE} -m pip install --no-cache delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel
# So delocate can find the libs
export DYLD_LIBRARY_PATH=${DYLD_LIBRARY_PATH}:${script_dir}/../oneTBB-prefix/lib

# Compile wheels re-using standalone project and archive cache
for VENV in "${VENVS[@]}"; do
    py_mm=$(basename ${VENV})
    Python3_EXECUTABLE=${VENV}/bin/python
    Python3_INCLUDE_DIR=$( find -L ${MACPYTHON_PY_PREFIX}/${py_mm}/include -name Python.h -exec dirname {} \; )

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"

    if [[ $(arch) == "arm64" ]]; then
      plat_name="macosx-11.0-arm64"
      osx_target="11.0"
      osx_arch="arm64"
      build_path="${SCRIPT_DIR}/../ITK-${py_mm}-macosx_arm64"
    else
      plat_name="macosx-10.9-x86_64"
      osx_target="10.9"
      osx_arch="x86_64"
      build_path="${SCRIPT_DIR}/../ITK-${py_mm}-macosx_x86_64"
    fi

    if [[ -e $PWD/requirements-dev.txt ]]; then
      ${Python3_EXECUTABLE} -m pip install --upgrade -r $PWD/requirements-dev.txt
    fi
    itk_build_path="${build_path}"
    ${Python3_EXECUTABLE} setup.py bdist_wheel --build-type Release --plat-name ${plat_name} -G Ninja -- \
      -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
      -DITK_DIR:PATH=${itk_build_path} \
      -DITK_USE_SYSTEM_SWIG:BOOL=ON \
      -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
      -DSWIG_EXECUTABLE:FILEPATH=${itk_build_path}/Wrapping/Generators/SwigInterface/swig/bin/swig \
      -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${osx_target} \
      -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
      -DBUILD_TESTING:BOOL=OFF \
      -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
      -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
    || exit 1
    # ${Python3_EXECUTABLE} setup.py clean    # Permission denied
done

for wheel in $PWD/dist/*.whl; do
  ${DELOCATE_PATCH} $wheel ${script_dir}/delocate.package.apply.patch # workaround for delocate's need for a package
  ${DELOCATE_LISTDEPS} $wheel # lists library dependencies
  ${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
  ${DELOCATE_PATCH} $wheel ${script_dir}/delocate.package.revert.patch # workaround for delocate's need for a package
done
