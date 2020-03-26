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
Python3_LIBRARY=""
SCRIPT_DIR=""
VENVS=()

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/macpython-build-common.sh"
# -----------------------------------------------------------------------

VENV="${VENVS[0]}"
Python3_EXECUTABLE=${VENV}/bin/python
${Python3_EXECUTABLE} -m pip install --no-cache cmake
# CMAKE_EXECUTABLE=${VENV}/bin/cmake
${Python3_EXECUTABLE} -m pip install --no-cache ninja
NINJA_EXECUTABLE=${VENV}/bin/ninja
${Python3_EXECUTABLE} -m pip install --no-cache delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel

# Compile wheels re-using standalone project and archive cache
for VENV in "${VENVS[@]}"; do
    py_mm=$(basename ${VENV})
    Python3_EXECUTABLE=${VENV}/bin/python
    Python3_INCLUDE_DIR=$( find -L ${MACPYTHON_PY_PREFIX}/${py_mm}/include -name Python.h -exec dirname {} \; )
    Python3_INCLUDE_DIRS=${Python3_INCLUDE_DIR}

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"
    echo "Python3_INCLUDE_DIRS:${Python3_INCLUDE_DIRS}"
    echo "Python3_LIBRARY:${Python3_LIBRARY}"

    if [[ -e $PWD/requirements-dev.txt ]]; then
      ${Python3_EXECUTABLE} -m pip install --upgrade -r $PWD/requirements-dev.txt
    fi
    itk_build_path="${SCRIPT_DIR}/../ITK-${py_mm}-macosx_x86_64"
    ${Python3_EXECUTABLE} setup.py bdist_wheel --build-type Release --plat-name macosx-10.9-x86_64 -G Ninja -- \
      -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
      -DITK_DIR:PATH=${itk_build_path} \
      -DITK_USE_SYSTEM_SWIG:BOOL=ON \
      -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
      -DSWIG_EXECUTABLE:FILEPATH=${itk_build_path}/Wrapping/Generators/SwigInterface/swig/bin/swig \
      -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=10.9 \
      -DCMAKE_OSX_ARCHITECTURES:STRING=x86_64 \
      -DBUILD_TESTING:BOOL=OFF \
      -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
      -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
      -DPython3_INCLUDE_DIRS:PATH=${Python3_INCLUDE_DIRS} \
    || exit 1
    ${Python3_EXECUTABLE} setup.py clean
done

${DELOCATE_LISTDEPS} $PWD/dist/*.whl # lists library dependencies
${DELOCATE_WHEEL} $PWD/dist/*.whl # copies library dependencies into wheel
