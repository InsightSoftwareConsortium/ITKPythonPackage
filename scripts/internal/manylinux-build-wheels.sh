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

    ${PYBIN}/pip install -r /work/requirements-dev.txt
    build_path=/work/ITK-$(basename $(dirname ${PYBIN}))-manylinux1_${arch}
    # Clean up previous invocations
    rm -rf $build_path
    ${PYBIN}/python setup.py bdist_wheel --build-type MinSizeRel -G Ninja -- \
      -DITK_SOURCE_DIR:PATH=/work/standalone-${arch}-build/ITK-source \
      -DITK_BINARY_DIR:PATH=${build_path} \
      -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
      -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
      -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY}
    ${PYBIN}/python setup.py clean
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
