#!/usr/bin/env bash

# -----------------------------------------------------------------------
# These variables are set in common script:
#
ARCH=""
PYBINARIES=""
PYTHON_LIBRARY=""

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/manylinux-build-common.sh"
# Install prerequirements
mkdir -p /work/tools
pushd /work/tools > /dev/null 2>&1
curl https://data.kitware.com/api/v1/file/5c0aa4b18d777f2179dd0a71/download -o doxygen-1.8.11.linux.bin.tar.gz
tar -xvzf doxygen-1.8.11.linux.bin.tar.gz
popd > /dev/null 2>&1
# -----------------------------------------------------------------------

# Build standalone project and populate archive cache
mkdir -p /work/standalone-${ARCH}-build
pushd /work/standalone-${ARCH}-build > /dev/null 2>&1
  cmake -DITKPythonPackage_BUILD_PYTHON:PATH=0 -G Ninja ../
  ninja
popd > /dev/null 2>&1

SINGLE_WHEEL=0

# Compile wheels re-using standalone project and archive cache
for PYBIN in "${PYBINARIES[@]}"; do
    export PYTHON_EXECUTABLE=${PYBIN}/python
    PYTHON_INCLUDE_DIR=$( find -L ${PYBIN}/../include/ -name Python.h -exec dirname {} \; )

    echo ""
    echo "PYTHON_EXECUTABLE:${PYTHON_EXECUTABLE}"
    echo "PYTHON_INCLUDE_DIR:${PYTHON_INCLUDE_DIR}"
    echo "PYTHON_LIBRARY:${PYTHON_LIBRARY}"

    # Install dependencies
    ${PYBIN}/pip install --upgrade -r /work/requirements-dev.txt

    build_type=MinSizeRel
    source_path=/work/standalone-${ARCH}-build/ITK-source
    build_path=/work/ITK-$(basename $(dirname ${PYBIN}))-manylinux1_${ARCH}
    SETUP_PY_CONFIGURE="${script_dir}/../setup_py_configure.py"
    SKBUILD_CMAKE_INSTALL_PREFIX=$(${PYTHON_EXECUTABLE} -c "from skbuild.constants import CMAKE_INSTALL_DIR; print(CMAKE_INSTALL_DIR)")

    # Clean up previous invocations
    rm -rf ${build_path}

    if [[ ${SINGLE_WHEEL} == 1 ]]; then

      echo "#"
      echo "# Build single ITK wheel"
      echo "#"

      # Configure setup.py
      ${PYBIN}/python ${SETUP_PY_CONFIGURE} "itk"
      # Generate wheel
      ${PYBIN}/python setup.py bdist_wheel --build-type ${build_type} -G Ninja -- \
            -DITK_SOURCE_DIR:PATH=${source_path} \
            -DITK_BINARY_DIR:PATH=${build_path} \
            -DITKPythonPackage_ITK_BINARY_REUSE:BOOL=OFF \
            -DITKPythonPackage_WHEEL_NAME:STRING="itk" \
            -DITK_WRAP_unsigned_short:BOOL=ON \
            -DCMAKE_CXX_COMPILER_TARGET:STRING=$(uname -p)-linux-gnu \
            -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
            -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
            -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY} \
            -DITK_WRAP_DOC:BOOL=ON \
            -DDOXYGEN_EXECUTABLE:FILEPATH=/work/tools/doxygen-1.8.11/bin/doxygen
      # Cleanup
      ${PYBIN}/python setup.py clean

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
          -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
          -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
          -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY} \
          -DCMAKE_CXX_COMPILER_TARGET:STRING=$(uname -p)-linux-gnu \
          -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
          -DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON \
          -DITK_WRAP_unsigned_short:BOOL=ON \
          -DPY_SITE_PACKAGES_PATH:PATH="." \
          -DITK_LEGACY_SILENT:BOOL=ON \
          -DITK_WRAP_PYTHON:BOOL=ON \
          -DITK_WRAP_PYTHON_LEGACY:BOOL=OFF \
          -DITK_WRAP_DOC:BOOL=ON \
          -DDOXYGEN_EXECUTABLE:FILEPATH=/work/tools/doxygen-1.8.11/bin/doxygen \
          -G Ninja \
          ${source_path} \
        && ninja \
        || exit 1
      )

      wheel_names=$(cat ${script_dir}/../WHEEL_NAMES.txt)
      for wheel_name in ${wheel_names}; do
        # Configure setup.py
        ${PYBIN}/python ${SETUP_PY_CONFIGURE} ${wheel_name}
        # Generate wheel
        ${PYBIN}/python setup.py bdist_wheel --build-type ${build_type} -G Ninja -- \
          -DITK_SOURCE_DIR:PATH=${source_path} \
          -DITK_BINARY_DIR:PATH=${build_path} \
          -DITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON \
          -DITKPythonPackage_WHEEL_NAME:STRING=${wheel_name} \
          -DITK_WRAP_unsigned_short:BOOL=ON \
          -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
          -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
          -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY} \
          -DITK_WRAP_DOC:BOOL=ON \
          -DDOXYGEN_EXECUTABLE:FILEPATH=/work/tools/doxygen-1.8.11/bin/doxygen \
          || exit 1
        # Cleanup
        ${PYBIN}/python setup.py clean
      done
    fi

    # Remove unnecessary files for building against ITK
    find ${build_path} -name '*.cpp' -delete -o -name '*.xml' -delete
    rm -rf ${build_path}/Wrapping/Generators/castxml*
    find ${build_path} -name '*.o' -delete

done

# auditwheel contains a regression where it will consume the "itk" wheels.
/opt/python/cp37-cp37m/bin/pip3 install auditwheel==1.9.0
# Since there are no external shared libraries to bundle into the wheels
# this step will fixup the wheel switching from 'linux' to 'manylinux1' tag
for whl in dist/*linux_$(uname -p).whl; do
    /opt/python/cp37-cp37m/bin/auditwheel repair ${whl} -w /work/dist/
    rm ${whl}
done

# Install packages and test
for PYBIN in "${PYBINARIES[@]}"; do
    ${PYBIN}/pip install --user numpy
    ${PYBIN}/pip install itk --user --no-cache-dir --no-index -f /work/dist
    (cd $HOME && ${PYBIN}/python -c 'from itk import ITKCommon;')
    (cd $HOME && ${PYBIN}/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
    (cd $HOME && ${PYBIN}/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
    (cd $HOME && ${PYBIN}/python ${script_dir}/../../docs/code/testDriver.py )
done
