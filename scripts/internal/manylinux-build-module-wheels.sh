#!/usr/bin/env bash

# -----------------------------------------------------------------------
# These variables are set in common script:
#
ARCH=""
PYBINARIES=""

script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/manylinux-build-common.sh"
# -----------------------------------------------------------------------

# Compile wheels re-using standalone project and archive cache
for PYBIN in "${PYBINARIES[@]}"; do
    Python3_EXECUTABLE=${PYBIN}/python
    Python3_INCLUDE_DIR=$( find -L ${PYBIN}/../include/ -name Python.h -exec dirname {} \; )

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"

    if [[ -e /work/requirements-dev.txt ]]; then
      ${PYBIN}/pip install --upgrade -r /work/requirements-dev.txt
    fi
    version=$(basename $(dirname ${PYBIN}))
    # Remove "m" -- not present in Python 3.8 and later
    version=${version:0:9}
    itk_build_dir=/work/$(basename /ITKPythonPackage/ITK-${version}*-manylinux2014_${ARCH})
    ln -fs /ITKPythonPackage/ITK-${version}*-manylinux2014_${ARCH} $itk_build_dir
    if [[ ! -d ${itk_build_dir} ]]; then
      echo 'ITK build tree not available!' 1>&2
      exit 1
    fi
    itk_source_dir=/work/ITK-source/ITK
    ln -fs /ITKPythonPackage/ITK-source/ /work/ITK-source
    if [[ ! -d ${itk_source_dir} ]]; then
      echo 'ITK source tree not available!' 1>&2
      exit 1
    fi
    ${PYBIN}/python setup.py bdist_wheel --build-type Release -G Ninja -- \
      -DITK_DIR:PATH=${itk_build_dir} \
      -DITK_USE_SYSTEM_SWIG:BOOL=ON \
      -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
      -DSWIG_EXECUTABLE:FILEPATH=${itk_build_dir}/Wrapping/Generators/SwigInterface/swig/bin/swig \
      -DCMAKE_CXX_COMPILER_TARGET:STRING=$(uname -p)-linux-gnu \
      -DBUILD_TESTING:BOOL=OFF \
      -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
      -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
    || exit 1
    ${PYBIN}/python setup.py clean
done

if test "${ARCH}" == "x64"; then
  for whl in dist/*linux_$(uname -p).whl; do
    auditwheel repair ${whl} -w /work/dist/
    rm ${whl}
  done
fi
for itk_wheel in dist/itk*-linux*.whl; do
  mv ${itk_wheel} ${itk_wheel/linux/manylinux2014}
done
