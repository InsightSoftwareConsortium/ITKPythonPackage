#!/usr/bin/env bash
set -e -x
MACPYTHON_PY_PREFIX=/Library/Frameworks/Python.framework/Versions
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Versions can be restricted by passing them in as arguments to the script
# For example,
# macpython-build-wheels.sh 2.7 3.5
if [[ $# -eq 0 ]]; then
  PYBINARIES=(${MACPYTHON_PY_PREFIX}/*)
else
  PYBINARIES=()
  for version in "$@"; do
    PYBINARIES+=(${MACPYTHON_PY_PREFIX}/*${version}*)
  done
fi

# Remove previous virtualenv's
rm -rf ${SCRIPT_DIR}/../venvs
# Create virtualenv's
VENVS=()
mkdir -p ${SCRIPT_DIR}/../venvs
for PYBIN in "${PYBINARIES[@]}"; do
    py_mm=$(basename ${PYBIN})
    VENV=${SCRIPT_DIR}/../venvs/${py_mm}
    VIRTUALENV_EXECUTABLE=${PYBIN}/bin/virtualenv
    ${VIRTUALENV_EXECUTABLE} $VENV
    VENVS+=(${VENV})
done

# Install CMake, Ninja
VENV="${VENVS[0]}"
PYTHON_EXECUTABLE=${VENV}/bin/python
$PYTHON_EXECUTABLE -m pip install cmake
CMAKE_EXECUTABLE=${VENV}/bin/cmake
$PYTHON_EXECUTABLE -m pip install ninja
NINJA_EXECUTABLE=${VENV}/bin/ninja
$PYTHON_EXECUTABLE -m pip install delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel


# Build standalone project and populate archive cache
mkdir -p standalone-build
pushd standalone-build > /dev/null 2>&1
  $CMAKE_EXECUTABLE -DITKPythonPackage_BUILD_PYTHON:PATH=0 \
    -G Ninja \
    -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
      ${SCRIPT_DIR}/../
  $NINJA_EXECUTABLE
popd > /dev/null 2>&1

# Since the python interpreter exports its symbol (see [1]), python
# modules should not link against any python libraries.
# To ensure it is not the case, we configure the project using an empty
# file as python library.
#
# [1] "Note that libpythonX.Y.so.1 is not on the list of libraries that
# a manylinux1 extension is allowed to link to. Explicitly linking to
# libpythonX.Y.so.1 is unnecessary in almost all cases: the way ELF linking
# works, extension modules that are loaded into the interpreter automatically
# get access to all of the interpreter's symbols, regardless of whether or
# not the extension itself is explicitly linked against libpython. [...]"
#
# Source: https://www.python.org/dev/peps/pep-0513/#libpythonx-y-so-1
PYTHON_LIBRARY=${SCRIPT_DIR}/internal/manylinux-libpython-not-needed-symbols-exported-by-interpreter
touch ${PYTHON_LIBRARY}

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
    $PYTHON_EXECUTABLE setup.py bdist_wheel --build-type MinSizeRel --plat-name macosx-10.6-x86_64 -G Ninja -- \
      -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
      -DITK_SOURCE_DIR:PATH=${SCRIPT_DIR}/../standalone-build/ITK-source \
      -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=10.6 \
      -DCMAKE_OSX_ARCHITECTURES:STRING=x86_64 \
      -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
      -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
      -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY}
    $PYTHON_EXECUTABLE setup.py clean
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
