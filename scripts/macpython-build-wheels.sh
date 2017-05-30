#!/usr/bin/env bash

# Run this script to build the ITK Python wheel packages for macOS.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/macpython-build-wheels.sh 2.7 3.5

script_dir="`cd $(dirname $0); pwd`"
source "${script_dir}/macpython-build-common.sh"

# Remove previous virtualenv's
rm -rf ${SCRIPT_DIR}/../venvs
# Create virtualenv's
VENVS=()
mkdir -p ${SCRIPT_DIR}/../venvs
for PYBIN in "${PYBINARIES[@]}"; do
    if [[ $(basename $PYBIN) = "Current" ]]; then
      continue
    fi
    py_mm=$(basename ${PYBIN})
    VENV=${SCRIPT_DIR}/../venvs/${py_mm}
    VIRTUALENV_EXECUTABLE=${PYBIN}/bin/virtualenv
    ${VIRTUALENV_EXECUTABLE} $VENV
    VENVS+=(${VENV})
done

# Build standalone project and populate archive cache
mkdir -p standalone-build
pushd standalone-build > /dev/null 2>&1
  $CMAKE_EXECUTABLE -DITKPythonPackage_BUILD_PYTHON:PATH=0 \
    -G Ninja \
    -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
      ${SCRIPT_DIR}/../
  $NINJA_EXECUTABLE
popd > /dev/null 2>&1

# Compile wheels re-using standalone project and archive cache
for VENV in "${VENVS[@]}"; do
    py_mm=$(basename ${VENV})
    PYTHON_EXECUTABLE=${VENV}/bin/python
    PYTHON_INCLUDE_DIR=$( find -L ${MACPYTHON_PY_PREFIX}/${py_mm}/include -name Python.h -exec dirname {} \; )

    echo ""
    echo "PYTHON_EXECUTABLE:${PYTHON_EXECUTABLE}"
    echo "PYTHON_INCLUDE_DIR:${PYTHON_INCLUDE_DIR}"
    echo "PYTHON_LIBRARY:${PYTHON_LIBRARY}"

    $PYTHON_EXECUTABLE -m pip install -r ${SCRIPT_DIR}/../requirements-dev.txt
    build_path="${SCRIPT_DIR}/../ITK-${py_mm}-macosx_x86_64"
    # Clean up previous invocations
    rm -rf $build_path
    $PYTHON_EXECUTABLE setup.py bdist_wheel --build-type MinSizeRel --plat-name macosx-10.6-x86_64 -G Ninja -- \
      -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
      -DITK_SOURCE_DIR:PATH=${SCRIPT_DIR}/../standalone-build/ITK-source \
      -DITK_BINARY_DIR:PATH=${build_path} \
      -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=10.6 \
      -DCMAKE_OSX_ARCHITECTURES:STRING=x86_64 \
      -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
      -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
      -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY}
    $PYTHON_EXECUTABLE setup.py clean
    # Remove unecessary files for building against ITK
    find $build_path -name '*.cpp' -delete -o -name '*.xml' -delete
    rm -rf $build_path/Wrapping/Generators/castxml*
    find $build_path -name '*.o' -delete
done

$DELOCATE_LISTDEPS ${SCRIPT_DIR}/../dist/*.whl # lists library dependencies
$DELOCATE_WHEEL ${SCRIPT_DIR}/../dist/*.whl # copies library dependencies into wheel

# Install packages and test
for VENV in "${VENVS[@]}"; do
    ${VENV}/bin/pip install itk --no-cache-dir --no-index -f ${SCRIPT_DIR}/../dist
    ${VENV}/bin/pip install numpy
    (cd $HOME; ${VENV}/bin/python -c 'import itk;')
    (cd $HOME; ${VENV}/bin/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
    (cd $HOME; ${VENV}/bin/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
done
