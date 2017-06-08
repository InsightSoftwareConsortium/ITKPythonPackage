#!/usr/bin/env bash

# -----------------------------------------------------------------------
# These variables are set in common script:
#
ARCH=""
PYBINARIES=""
PYTHON_LIBRARY=""

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/manylinux-build-common.sh"
# -----------------------------------------------------------------------

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

    if [[ -e /work/requirements-dev.txt ]]; then
      ${PYBIN}/pip install --upgrade -r /work/requirements-dev.txt
    fi
    itk_build_dir=/work/ITK-$(basename $(dirname ${PYBIN}))-manylinux1_${ARCH}
    ln -fs /ITKPythonPackage/ITK-$(basename $(dirname ${PYBIN}))-manylinux1_${ARCH} $itk_build_dir
    if [[ ! -d ${itk_build_dir} ]]; then
      echo 'ITK build tree not available!' 1>&2
      exit 1
    fi
    itk_source_dir=/work/standalone-${ARCH}-build/ITK-source
    ln -fs /ITKPythonPackage/standalone-${ARCH}-build/ /work/standalone-${ARCH}-build
    if [[ ! -d ${itk_source_dir} ]]; then
      echo 'ITK source tree not available!' 1>&2
      exit 1
    fi
    ${PYBIN}/python setup.py bdist_wheel --build-type MinSizeRel -G Ninja -- \
      -DITK_DIR:PATH=${itk_build_dir} \
      -DITK_USE_SYSTEM_SWIG:BOOL=ON \
      -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
      -DSWIG_EXECUTABLE:FILEPATH=${itk_build_dir}/Wrapping/Generators/SwigInterface/swig/bin/swig \
      -DCMAKE_CXX_COMPILER_TARGET:STRING=$(uname -p)-linux-gnu \
      -DBUILD_TESTING:BOOL=OFF \
      -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
      -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
      -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY} \
    || exit 1
    ${PYBIN}/python setup.py clean
done

# Since there are no external shared libraries to bundle into the wheels
# this step will fixup the wheel switching from 'linux' to 'manylinux1' tag
for whl in dist/*linux_$(uname -p).whl; do
    auditwheel repair ${whl} -w /work/dist/
    rm ${whl}
done
