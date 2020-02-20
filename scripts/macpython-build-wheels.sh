#!/usr/bin/env bash

# Run this script to build the ITK Python wheel packages for macOS.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/macpython-build-wheels.sh 2.7 3.5

# -----------------------------------------------------------------------
# These variables are set in common script:
#
MACPYTHON_PY_PREFIX=""
PYBINARIES=""
Python3_LIBRARY=""
SCRIPT_DIR=""

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/macpython-build-common.sh"
# -----------------------------------------------------------------------
# Ensure that requirements are met
brew update
brew info doxygen | grep --quiet 'Not installed' && brew install doxygen
# -----------------------------------------------------------------------
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
    ${VIRTUALENV_EXECUTABLE} ${VENV}
    VENVS+=(${VENV})
done

VENV="${VENVS[0]}"
Python3_EXECUTABLE=${VENV}/bin/python
${Python3_EXECUTABLE} -m pip install --no-cache cmake
CMAKE_EXECUTABLE=${VENV}/bin/cmake
${Python3_EXECUTABLE} -m pip install --no-cache ninja
NINJA_EXECUTABLE=${VENV}/bin/ninja
${Python3_EXECUTABLE} -m pip install --no-cache delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel

# Build standalone project and populate archive cache
mkdir -p standalone-build
pushd standalone-build > /dev/null 2>&1
  ${CMAKE_EXECUTABLE} -DITKPythonPackage_BUILD_PYTHON:PATH=0 \
    -G Ninja \
    -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
      ${SCRIPT_DIR}/../
  ${NINJA_EXECUTABLE}
popd > /dev/null 2>&1

SINGLE_WHEEL=0

# Compile wheels re-using standalone project and archive cache
for VENV in "${VENVS[@]}"; do
    py_mm=$(basename ${VENV})
    export Python3_EXECUTABLE=${VENV}/bin/python
    Python3_INCLUDE_DIR=$( find -L ${MACPYTHON_PY_PREFIX}/${py_mm}/include -name Python.h -exec dirname {} \; )

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"
    echo "Python3_LIBRARY:${Python3_LIBRARY}"

    # Install dependencies
    ${Python3_EXECUTABLE} -m pip install --upgrade -r ${SCRIPT_DIR}/../requirements-dev.txt

    build_type="MinSizeRel"
    plat_name="macosx-10.9-x86_64"
    osx_target="10.9"
    source_path=${SCRIPT_DIR}/../standalone-build/ITKs
    build_path="${SCRIPT_DIR}/../ITK-${py_mm}-macosx_x86_64"
    SETUP_PY_CONFIGURE="${script_dir}/setup_py_configure.py"

    # Clean up previous invocations
    rm -rf ${build_path}

    if [[ ${SINGLE_WHEEL} == 1 ]]; then

      echo "#"
      echo "# Build single ITK wheel"
      echo "#"

      # Configure setup.py
      ${Python3_EXECUTABLE} ${SETUP_PY_CONFIGURE} "itk"
      # Generate wheel
      ${Python3_EXECUTABLE} setup.py bdist_wheel --build-type ${build_type} --plat-name ${plat_name} -G Ninja -- \
        -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
        -DITK_SOURCE_DIR:PATH= ${source_path} \
        -DITK_BINARY_DIR:PATH=${build_path} \
        -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${osx_target} \
        -DCMAKE_OSX_ARCHITECTURES:STRING=x86_64 \
        -DITK_WRAP_unsigned_short:BOOL=ON \
        -DITK_WRAP_double:BOOL=ON \
        -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        -DPython3_LIBRARY:FILEPATH=${Python3_LIBRARY} \
        -DITK_WRAP_DOC:BOOL=ON
      # Cleanup
      ${Python3_EXECUTABLE} setup.py clean

    else

      echo "#"
      echo "# Build multiple ITK wheels"
      echo "#"

      # Build ITK python
      (
        mkdir -p ${build_path} \
        && cd ${build_path} \
        && cmake \
          -DCMAKE_BUILD_TYPE:STRING=${build_type} \
          -DITK_SOURCE_DIR:PATH=${source_path} \
          -DITK_BINARY_DIR:PATH=${build_path} \
          -DBUILD_TESTING:BOOL=OFF \
          -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${osx_target} \
          -DCMAKE_OSX_ARCHITECTURES:STRING=x86_64 \
          -DITK_WRAP_unsigned_short:BOOL=ON \
          -DITK_WRAP_double:BOOL=ON \
          -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
          -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
          -DPython3_LIBRARY:FILEPATH=${Python3_LIBRARY} \
          -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
          -DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON \
          "-DPY_SITE_PACKAGES_PATH:PATH=." \
          -DITK_LEGACY_SILENT:BOOL=ON \
          -DITK_WRAP_PYTHON:BOOL=ON \
          -DITK_WRAP_DOC:BOOL=ON \
          -G Ninja \
          ${source_path} \
        && ninja\
        || exit 1
      )

      wheel_names=$(cat ${SCRIPT_DIR}/WHEEL_NAMES.txt)
      for wheel_name in ${wheel_names}; do
        # Configure setup.py
        ${Python3_EXECUTABLE} ${SETUP_PY_CONFIGURE} ${wheel_name}
        # Generate wheel
        ${Python3_EXECUTABLE} setup.py bdist_wheel --build-type ${build_type} --plat-name ${plat_name} -G Ninja -- \
          -DITK_SOURCE_DIR:PATH=${source_path} \
          -DITK_BINARY_DIR:PATH=${build_path} \
          -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${osx_target} \
          -DCMAKE_OSX_ARCHITECTURES:STRING=x86_64 \
          -DITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON \
          -DITKPythonPackage_WHEEL_NAME:STRING=${wheel_name} \
          -DITK_WRAP_unsigned_short:BOOL=ON \
          -DITK_WRAP_double:BOOL=ON \
          -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
          -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
          -DPython3_LIBRARY:FILEPATH=${Python3_LIBRARY} \
          -DITK_WRAP_DOC:BOOL=ON \
        || exit 1
        # Cleanup
        ${Python3_EXECUTABLE} setup.py clean
      done

    fi

    # Remove unnecessary files for building against ITK
    find ${build_path} -name '*.cpp' -delete -o -name '*.xml' -delete
    rm -rf ${build_path}/Wrapping/Generators/castxml*
    find ${build_path} -name '*.o' -delete
done

${DELOCATE_LISTDEPS} ${SCRIPT_DIR}/../dist/*.whl # lists library dependencies
${DELOCATE_WHEEL} ${SCRIPT_DIR}/../dist/*.whl # copies library dependencies into wheel

# Install packages and test
for VENV in "${VENVS[@]}"; do
    ${VENV}/bin/pip install numpy
    ${VENV}/bin/pip install itk --no-cache-dir --no-index -f ${SCRIPT_DIR}/../dist
    (cd $HOME && ${VENV}/bin/python -c 'import itk;')
    (cd $HOME && ${VENV}/bin/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
    (cd $HOME && ${VENV}/bin/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
    (cd $HOME && ${VENV}/bin/python ${SCRIPT_DIR}/../docs/code/testDriver.py )
done
