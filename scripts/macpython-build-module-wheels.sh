#!/usr/bin/env bash

# Run this script to build the Python wheel packages for macOS for an ITK
# external module.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/macpython-build-module-wheels.sh 2.7 3.5

# -----------------------------------------------------------------------
# These variables are set in common script:
#
MACPYTHON_PY_PREFIX=""
# PYBINARIES="" # unused
PYTHON_LIBRARY=""
SCRIPT_DIR=""
VENVS=()

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/macpython-build-common.sh"
# -----------------------------------------------------------------------

VENV="${VENVS[0]}"
PYTHON_EXECUTABLE=${VENV}/bin/python
${PYTHON_EXECUTABLE} -m pip install --no-cache cmake
# CMAKE_EXECUTABLE=${VENV}/bin/cmake
${PYTHON_EXECUTABLE} -m pip install --no-cache ninja
NINJA_EXECUTABLE=${VENV}/bin/ninja
${PYTHON_EXECUTABLE} -m pip install --no-cache delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel

# Compile wheels re-using standalone project and archive cache
for VENV in "${VENVS[@]}"; do
    py_mm=$(basename ${VENV})
    PYTHON_EXECUTABLE=${VENV}/bin/python
    PYTHON_INCLUDE_DIR=$( find -L ${MACPYTHON_PY_PREFIX}/${py_mm}/include -name Python.h -exec dirname {} \; )

    echo ""
    echo "PYTHON_EXECUTABLE:${PYTHON_EXECUTABLE}"
    echo "PYTHON_INCLUDE_DIR:${PYTHON_INCLUDE_DIR}"
    echo "PYTHON_LIBRARY:${PYTHON_LIBRARY}"

    if [[ -e $PWD/requirements-dev.txt ]]; then
      ${PYTHON_EXECUTABLE} -m pip install --upgrade -r $PWD/requirements-dev.txt
    fi
    ${PYTHON_EXECUTABLE} -m pip install --no-cache ninja
    NINJA_EXECUTABLE=${VENV}/bin/ninja
    itk_build_path="${SCRIPT_DIR}/../ITK-${py_mm}-macosx_x86_64"
    ${PYTHON_EXECUTABLE} setup.py bdist_wheel --build-type MinSizeRel --plat-name macosx-10.6-x86_64 -G Ninja -- \
      -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
      -DITK_DIR:PATH=${itk_build_path} \
      -DITK_USE_SYSTEM_SWIG:BOOL=ON \
      -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
      -DSWIG_EXECUTABLE:FILEPATH=${itk_build_path}/Wrapping/Generators/SwigInterface/swig/bin/swig \
      -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=10.6 \
      -DCMAKE_OSX_ARCHITECTURES:STRING=x86_64 \
      -DBUILD_TESTING:BOOL=OFF \
      -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
      -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
      -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY} \
    || exit 1
    ${PYTHON_EXECUTABLE} setup.py clean
done

# Temporarily disabled. See Issue
# @InsightSoftwareConsortium/ITKPythonPackage#78
#${DELOCATE_LISTDEPS} $PWD/dist/*.whl # lists library dependencies
#${DELOCATE_WHEEL} $PWD/dist/*.whl # copies library dependencies into wheel
