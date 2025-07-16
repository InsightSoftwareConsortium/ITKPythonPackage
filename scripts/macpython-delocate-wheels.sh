#!/usr/bin/env bash

# Run this script to build the ITK Python wheel packages for macOS.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/macpython-build-wheels.sh 3.9
#
# Shared libraries can be included in the wheel by exporting them to DYLD_LIBRARY_PATH before
# running this script.
# 
# For example,
#
#   export DYLD_LIBRARY_PATH="/path/to/libs"
#   scripts/macpython-build-module-wheels.sh 3.9
#

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
    VIRTUALENV_EXECUTABLE="${PYBIN}/bin/python3 -m venv"
    ${VIRTUALENV_EXECUTABLE} ${VENV}
    VENVS+=(${VENV})
done

VENV="${VENVS[0]}"
Python3_EXECUTABLE=${VENV}/bin/python3
${Python3_EXECUTABLE} -m pip install --no-cache delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel
DELOCATE_PATCH=${VENV}/bin/delocate-patch

build_type="Release"

if [[ $(arch) == "arm64" ]]; then
  osx_target="15.0"
  osx_arch="arm64"
  use_tbb="OFF"
else
  osx_target="15.0"
  osx_arch="x86_64"
  use_tbb="OFF"
fi

for wheel in dist/*.whl; do
  echo "Delocating $wheel"
  #if [[ $wheel = *itk_core* ]]; then
    ${DELOCATE_LISTDEPS} $wheel # lists library dependencies
    ${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
  #else
    #${DELOCATE_PATCH} $wheel ${SCRIPT_DIR}/delocate.package.apply.patch # workaround for delocate's need for a package
    #${DELOCATE_LISTDEPS} $wheel # lists library dependencies
    #${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
    #${DELOCATE_PATCH} $wheel ${SCRIPT_DIR}/delocate.package.revert.patch # workaround for delocate's need for a package
  #fi
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
