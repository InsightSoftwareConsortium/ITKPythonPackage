#!/usr/bin/env bash

# Run this script to build the ITK Python wheel packages for macOS.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/macpython-build-wheels.sh 3.9

# -----------------------------------------------------------------------
# These variables are set in common script:
#
MACPYTHON_PY_PREFIX=""
PYBINARIES=""
SCRIPT_DIR=""

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/macpython-build-common.sh"

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
Python3_EXECUTABLE=${VENV}/bin/python3
${Python3_EXECUTABLE} -m pip install --no-cache delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel
DELOCATE_PATCH=${VENV}/bin/delocate-patch

# Build standalone project and populate archive cache
tbb_dir=$PWD/oneTBB-prefix/lib/cmake/TBB
# So delocate can find the libs
export DYLD_LIBRARY_PATH=$PWD/oneTBB-prefix/lib
mkdir -p ITK-source
pushd ITK-source > /dev/null 2>&1
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

    ${Python3_EXECUTABLE} -m pip install --upgrade -r ${SCRIPT_DIR}/../requirements-dev.txt

    build_type="Release"
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
    source_path=${SCRIPT_DIR}/../ITK-source/ITK
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
        -DITK_SOURCE_DIR:PATH=${source_path} \
        -DITK_BINARY_DIR:PATH=${build_path} \
        -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${osx_target} \
        -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
        -DITK_WRAP_unsigned_short:BOOL=ON \
        -DITK_WRAP_double:BOOL=ON \
        -DITK_WRAP_complex_double:BOOL=ON \
        -DITK_WRAP_IMAGE_DIMS:STRING="2;3;4" \
        -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        -DModule_ITKTBB:BOOL=ON \
        -DTBB_DIR:PATH=${tbb_dir} \
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
          -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
          -DITK_WRAP_unsigned_short:BOOL=ON \
          -DITK_WRAP_double:BOOL=ON \
          -DITK_WRAP_complex_double:BOOL=ON \
          -DITK_WRAP_IMAGE_DIMS:STRING="2;3;4" \
          -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
          -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
          -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
          -DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON \
          "-DPY_SITE_PACKAGES_PATH:PATH=." \
          -DITK_LEGACY_SILENT:BOOL=ON \
          -DITK_WRAP_PYTHON:BOOL=ON \
          -DITK_WRAP_DOC:BOOL=ON \
          -DModule_ITKTBB:BOOL=ON \
          -DTBB_DIR:PATH=${tbb_dir} \
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
          -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
          -DITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON \
          -DITKPythonPackage_WHEEL_NAME:STRING=${wheel_name} \
          -DITK_WRAP_unsigned_short:BOOL=ON \
          -DITK_WRAP_double:BOOL=ON \
          -DITK_WRAP_complex_double:BOOL=ON \
          -DITK_WRAP_IMAGE_DIMS:STRING="2;3;4" \
          -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
          -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
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

for wheel in dist/*.whl; do
  echo "Delocating $wheel"
  if [[ $wheel = *itk_core* ]]; then
    ${DELOCATE_LISTDEPS} $wheel # lists library dependencies
    ${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
  else
    ${DELOCATE_PATCH} $wheel ${SCRIPT_DIR}/delocate.package.apply.patch # workaround for delocate's need for a package
    ${DELOCATE_LISTDEPS} $wheel # lists library dependencies
    ${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
    ${DELOCATE_PATCH} $wheel ${SCRIPT_DIR}/delocate.package.revert.patch # workaround for delocate's need for a package
  fi
done

# Install packages and test
# numpy wheel not currently available for the M1
# https://github.com/numpy/numpy/issues/17807
if [[ $(arch) != "arm64" ]]; then
  for VENV in "${VENVS[@]}"; do
      ${VENV}/bin/pip install numpy
      ${VENV}/bin/pip install itk --no-cache-dir --no-index -f ${SCRIPT_DIR}/../dist
      (cd $HOME && ${VENV}/bin/python -c 'import itk;')
      (cd $HOME && ${VENV}/bin/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
      (cd $HOME && ${VENV}/bin/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
      (cd $HOME && ${VENV}/bin/python ${SCRIPT_DIR}/../docs/code/test.py )
  done
fi
