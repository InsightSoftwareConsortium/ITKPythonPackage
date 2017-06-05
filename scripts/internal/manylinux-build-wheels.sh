#!/usr/bin/env bash

script_dir="`cd $(dirname $0); pwd`"
source "${script_dir}/manylinux-build-common.sh"

# Build standalone project and populate archive cache
mkdir -p /work/standalone-${arch}-build
pushd /work/standalone-${arch}-build > /dev/null 2>&1
  cmake -DITKPythonPackage_BUILD_PYTHON:PATH=0 -G Ninja ../
  ninja
popd > /dev/null 2>&1

# Compile wheels re-using standalone project and archive cache
for PYBIN in "${PYBINARIES[@]}"; do
    if [[ ${PYBIN} == *"cp26"* || ${PYBIN} == *"cp33"* ]]; then
        echo "Skipping ${PYBIN}"
        continue
    fi

    PYTHON_EXECUTABLE=${PYBIN}/python
    PYTHON_INCLUDE_DIR=$( find -L ${PYBIN}/../include/ -name Python.h -exec dirname {} \; )

    echo ""
    echo "PYTHON_EXECUTABLE:${PYTHON_EXECUTABLE}"
    echo "PYTHON_INCLUDE_DIR:${PYTHON_INCLUDE_DIR}"
    echo "PYTHON_LIBRARY:${PYTHON_LIBRARY}"

    # Install dependencies
    ${PYBIN}/pip install -r /work/requirements-dev.txt

    build_type=MinSizeRel
    source_path=/work/standalone-${arch}-build/ITK-source
    build_path=/work/ITK-$(basename $(dirname ${PYBIN}))-manylinux1_${arch}
    SETUP_PY_CONFIGURE="${script_dir}/../setup_py_configure.py"

    # Clean up previous invocations
    rm -rf ${build_path}

    single_wheel=0

    if [[ ${single_wheel} == 1 ]]; then

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
            -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
            -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
            -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY}
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
          -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
          -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
          -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY} \
          -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
          -DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON \
          -DPY_SITE_PACKAGES_PATH:PATH=${SCRIPT_DIR}/../_skbuild/cmake-install \
          -DITK_LEGACY_SILENT:BOOL=ON \
          -DITK_WRAP_PYTHON:BOOL=ON \
          -DITK_WRAP_PYTHON_LEGACY:BOOL=OFF \
          -G Ninja \
          ${source_path} \
        && ninja
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
          -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
          -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
          -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY}
        # Cleanup
        ${PYBIN}/python setup.py clean
      done
    fi

    # Remove unecessary files for building against ITK
    find $build_path -name '*.cpp' -delete -o -name '*.xml' -delete
    rm -rf $build_path/Wrapping/Generators/castxml*
    find $build_path -name '*.o' -delete

done

# Since there are no external shared libraries to bundle into the wheels
# this step will fixup the wheel switching from 'linux' to 'manylinux1' tag
for whl in dist/*linux_$(uname -p).whl; do
    auditwheel repair $whl -w /work/dist/
    rm $whl
done

# Install packages and test
for PYBIN in "${PYBINARIES[@]}"; do
    if [[ ${PYBIN} == *"cp26"* || ${PYBIN} == *"cp33"* ]]; then
        echo "Skipping ${PYBIN}"
        continue
    fi
    sudo ${PYBIN}/pip install itk --no-cache-dir --no-index -f /work/dist
    sudo ${PYBIN}/pip install numpy
    (cd $HOME; ${PYBIN}/python -c 'from itk import ITKCommon;')
    (cd $HOME; ${PYBIN}/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
    (cd $HOME; ${PYBIN}/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
done
