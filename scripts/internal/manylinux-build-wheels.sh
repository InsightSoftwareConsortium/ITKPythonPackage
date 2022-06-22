#!/usr/bin/env bash

# Run this script inside a dockcross container to build Python wheels for ITK.
#
# Versions can be restricted by passing them in as arguments to the script.
# For example,
#
#   /tmp/dockcross-manylinux-x64 manylinux-build-wheels.sh cp39
#
# Shared library dependencies can be included wheels by mounting them to /usr/lib64 or /usr/local/lib64 
# before running this script.
# 
# For example,
#
#   DOCKER_ARGS="-v /path/to/lib.so:/usr/local/lib64/lib.so"
#   /tmp/dockcross-manylinux-x64 -a "$DOCKER_ARGS" manylinux-build-wheels.sh
#

# -----------------------------------------------------------------------
# These variables are set in common script:
#
ARCH=""
PYBINARIES=""
Python3_LIBRARY=""

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/manylinux-build-common.sh"

# -----------------------------------------------------------------------

# Build standalone project and populate archive cache
mkdir -p /work/ITK-source
pushd /work/ITK-source > /dev/null 2>&1
  cmake -DITKPythonPackage_BUILD_PYTHON:PATH=0 -G Ninja ../
  ninja
popd > /dev/null 2>&1
tbb_dir=/work/oneTBB-prefix/lib64/cmake/TBB
# So auditwheel can find the libs
sudo ldconfig
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/work/oneTBB-prefix/lib64:/usr/lib:/usr/lib64

SINGLE_WHEEL=0

# Compile wheels re-using standalone project and archive cache
for PYBIN in "${PYBINARIES[@]}"; do
    export Python3_EXECUTABLE=${PYBIN}/python3
    Python3_INCLUDE_DIR=$( find -L ${PYBIN}/../include/ -name Python.h -exec dirname {} \; )

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"

    # Install dependencies
    ${PYBIN}/pip install --upgrade -r /work/requirements-dev.txt

    build_type="Release"
    compile_flags="-O3 -DNDEBUG"
    source_path=/work/ITK-source/ITK
    build_path=/work/ITK-$(basename $(dirname ${PYBIN}))-manylinux${MANYLINUX_VERSION}_${ARCH}
    SETUP_PY_CONFIGURE="${script_dir}/../setup_py_configure.py"
    SKBUILD_CMAKE_INSTALL_PREFIX=$(${Python3_EXECUTABLE} -c "from skbuild.constants import CMAKE_INSTALL_DIR; print(CMAKE_INSTALL_DIR)")

    # Clean up previous invocations
    rm -rf ${build_path}

    if [[ ${SINGLE_WHEEL} == 1 ]]; then

      echo "#"
      echo "# Build single ITK wheel"
      echo "#"

      # Configure setup.py
      ${PYBIN}/python ${SETUP_PY_CONFIGURE} "itk"
      # Generate wheel
      ${PYBIN}/python setup.py bdist_wheel -G Ninja -- \
            -DITK_SOURCE_DIR:PATH=${source_path} \
            -DITK_BINARY_DIR:PATH=${build_path} \
            -DITKPythonPackage_ITK_BINARY_REUSE:BOOL=OFF \
            -DITKPythonPackage_WHEEL_NAME:STRING="itk" \
            -DITK_WRAP_unsigned_short:BOOL=ON \
            -DITK_WRAP_double:BOOL=ON \
            -DITK_WRAP_complex_double:BOOL=ON \
            -DITK_WRAP_IMAGE_DIMS:STRING="2;3;4" \
            -DCMAKE_CXX_COMPILER_TARGET:STRING=$(uname -p)-linux-gnu \
            -DCMAKE_CXX_FLAGS:STRING="$compile_flags" \
            -DCMAKE_C_FLAGS:STRING="$compile_flags" \
            -DCMAKE_BUILD_TYPE:STRING="${build_type}" \
            -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
            -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
            -DModule_ITKTBB:BOOL=ON \
            -DTBB_DIR:PATH=${tbb_dir} \
            -DITK_WRAP_DOC:BOOL=ON
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
          -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
          -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
          -DCMAKE_CXX_COMPILER_TARGET:STRING=$(uname -p)-linux-gnu \
          -DCMAKE_CXX_FLAGS:STRING="$compile_flags" \
          -DCMAKE_C_FLAGS:STRING="$compile_flags" \
          -DCMAKE_BUILD_TYPE:STRING="${build_type}" \
          -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
          -DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON \
          -DITK_WRAP_unsigned_short:BOOL=ON \
          -DITK_WRAP_double:BOOL=ON \
          -DITK_WRAP_complex_double:BOOL=ON \
          -DITK_WRAP_IMAGE_DIMS:STRING="2;3;4" \
          -DPY_SITE_PACKAGES_PATH:PATH="." \
          -DITK_LEGACY_SILENT:BOOL=ON \
          -DITK_WRAP_PYTHON:BOOL=ON \
          -DITK_WRAP_DOC:BOOL=ON \
          -DModule_ITKTBB:BOOL=ON \
          -DTBB_DIR:PATH=${tbb_dir} \
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
        ${PYBIN}/python setup.py bdist_wheel -G Ninja -- \
          -DITK_SOURCE_DIR:PATH=${source_path} \
          -DITK_BINARY_DIR:PATH=${build_path} \
          -DITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON \
          -DITKPythonPackage_WHEEL_NAME:STRING=${wheel_name} \
          -DITK_WRAP_unsigned_short:BOOL=ON \
          -DITK_WRAP_double:BOOL=ON \
          -DITK_WRAP_complex_double:BOOL=ON \
          -DITK_WRAP_IMAGE_DIMS:STRING="2;3;4" \
          -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
          -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
          -DCMAKE_BUILD_TYPE:STRING="${build_type}" \
          -DCMAKE_CXX_FLAGS:STRING="${compile_flags}" \
          -DCMAKE_C_FLAGS:STRING="${compile_flags}" \
          -DITK_WRAP_DOC:BOOL=ON \
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

if test "${ARCH}" == "x64"; then
  sudo /opt/python/cp39-cp39/bin/pip3 install auditwheel wheel
  # This step will fixup the wheel switching from 'linux' to 'manylinux<version>' tag
  for whl in dist/itk_*linux_$(uname -p).whl; do
      /opt/python/cp39-cp39/bin/auditwheel repair --plat manylinux${MANYLINUX_VERSION}_x86_64 ${whl} -w /work/dist/
      rm ${whl}
  done
else
  for whl in dist/itk_*$(uname -p).whl; do
      auditwheel repair ${whl} -w /work/dist/
      rm ${whl}
  done
fi
itk_core_whl=$(ls dist/itk_core*whl | head -n 1)
repaired_plat1=$(echo $itk_core_whl | cut -d- -f5 | cut -d. -f1)
repaired_plat2=$(echo $itk_core_whl | cut -d- -f5 | cut -d. -f2)
for itk_wheel in dist/itk*-linux*.whl; do
  mkdir -p unpacked_whl packed_whl
  /opt/python/cp39-cp39/bin/wheel unpack -d unpacked_whl ${itk_wheel}
  version=$(echo ${itk_wheel} | cut -d- -f3-4)
  echo "Wheel-Version: 1.0" > unpacked_whl/itk-*/*.dist-info/WHEEL
  echo "Generator: skbuild 0.8.1" >> unpacked_whl/itk-*/*.dist-info/WHEEL
  echo "Root-Is-Purelib: false" >> unpacked_whl/itk-*/*.dist-info/WHEEL
  echo "Tag: ${version}-${repaired_plat1}" >> unpacked_whl/itk-*/*.dist-info/WHEEL
  echo "Tag: ${version}-${repaired_plat2}" >> unpacked_whl/itk-*/*.dist-info/WHEEL
  echo "" >> unpacked_whl/itk-*/*.dist-info/WHEEL
  /opt/python/cp39-cp39/bin/wheel pack -d packed_whl ./unpacked_whl/itk-*
  mv packed_whl/*.whl dist/
  rm -rf unpacked_whl packed_whl ${itk_wheel}
done

# Install packages and test
for PYBIN in "${PYBINARIES[@]}"; do
    ${PYBIN}/pip install --user numpy
    ${PYBIN}/pip install itk --user --no-cache-dir --no-index -f /work/dist
    (cd $HOME && ${PYBIN}/python -c 'from itk import ITKCommon;')
    (cd $HOME && ${PYBIN}/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
    (cd $HOME && ${PYBIN}/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
    (cd $HOME && ${PYBIN}/python ${script_dir}/../../docs/code/test.py )
done
