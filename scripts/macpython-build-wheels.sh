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
# These variables are set in macpython-build-common.sh script:
#
# * CMAKE_EXECUTABLE
# * CMAKE_OPTIONS
# * MACPYTHON_PY_PREFIX
# * PYBINARIES
# * PYTHON_VERSIONS
# * NINJA_EXECUTABLE
# * script_dir
# * VENVS=()
# * CMAKE_COMPILE_ARGS
script_dir=$(cd $(dirname $0) || exit 1; pwd)
_ipp_dir=$(dirname ${script_dir})
package_env_file=${_ipp_dir}/build/package.env
if [ ! -f "${package_env_file}" ]; then
  ${_ipp_dir}/generate_build_environment.sh -o ${package_env_file}
fi
source "${package_env_file}"

source "${script_dir}/macpython-build-common.sh"

# -----------------------------------------------------------------------
# Remove previous virtualenv's
rm -rf ${script_dir}/../venvs
# Create virtualenv's
VENVS=()
mkdir -p ${script_dir}/../venvs
for PYBIN in "${PYBINARIES[@]}"; do
    if [[ $(basename $PYBIN) = "Current" ]]; then
      continue
    fi
    py_mm=$(basename ${PYBIN})
    VENV=${script_dir}/../venvs/${py_mm}
    VIRTUALENV_EXECUTABLE="${PYBIN}/bin/python3 -m venv"
    ${VIRTUALENV_EXECUTABLE} ${VENV}
    VENVS+=(${VENV})
done

VENV="${VENVS[0]}"
Python3_EXECUTABLE=${VENV}/bin/python3
${Python3_EXECUTABLE} -m pip install --upgrade pip
${Python3_EXECUTABLE} -m pip install --no-cache-dir delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel

build_type="Release"
MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET:="15.0"}

if [[ $(arch) == "arm64" ]]; then
  osx_arch="arm64"
else
  osx_arch="x86_64"
fi

# Build standalone project and populate archive cache
n_processors=$(sysctl -n hw.ncpu)
# So delocate can find the libs
use_tbb="OFF"
if [[ "${use_tbb}" -eq "ON" ]]; then
  tbb_dir=$PWD/oneTBB-prefix/lib/cmake/TBB
  export DYLD_LIBRARY_PATH=${DYLD_LIBRARY_PATH}:${_ipp_dir}/oneTBB-prefix/lib
else
  tbb_dir="NOT-FOUND"
fi

mkdir -p ITK-source
pushd ITK-source > /dev/null 2>&1
  ${CMAKE_EXECUTABLE} -DITKPythonPackage_BUILD_PYTHON:PATH=0 \
    -DITKPythonPackage_USE_TBB:BOOL=${use_tbb} \
    -G Ninja \
    -DCMAKE_BUILD_TYPE:STRING=${build_type} \
    -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
    -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
    -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
    ${CMAKE_COMPILER_ARGS} \
      ${script_dir}/../
  ${NINJA_EXECUTABLE} -j$n_processors -l$n_processors
popd > /dev/null 2>&1

# Compile wheels re-using standalone project and archive cache
for VENV in "${VENVS[@]}"; do
    py_mm=$(basename ${VENV})
    export Python3_EXECUTABLE=${VENV}/bin/python
    Python3_INCLUDE_DIR=$( find -L ${MACPYTHON_PY_PREFIX}/${py_mm}/include -name Python.h -exec dirname {} \; )

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"

    ${Python3_EXECUTABLE} -m pip install --upgrade -r ${script_dir}/../requirements-dev.txt

    if [[ $(arch) == "arm64" ]]; then
      plat_name="macosx-15.0-arm64"
      build_path="${script_dir}/../ITK-${py_mm}-macosx_arm64"
    else
      plat_name="macosx-15.0-x86_64"
      build_path="${script_dir}/../ITK-${py_mm}-macosx_x86_64"
    fi
    source_path=${script_dir}/../ITK-source/ITK

    # Clean up previous invocations
    rm -rf ${build_path}

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
        -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
        -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
        ${CMAKE_COMPILER_ARGS} \
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
        -DModule_ITKTBB:BOOL=${use_tbb} \
        -DTBB_DIR:PATH=${tbb_dir} \
        ${CMAKE_OPTIONS} \
        -G Ninja \
        ${source_path} \
      && ninja -j$n_processors -l$n_processors \
      || exit 1
    )

    PYPROJECT_CONFIGURE="${script_dir}/pyproject_configure.py"
    wheel_names=$(cat ${script_dir}/WHEEL_NAMES.txt)
    for wheel_name in ${wheel_names}; do
      # Configure pyproject.toml
      ${Python3_EXECUTABLE} ${PYPROJECT_CONFIGURE} --env-file ${package_env_file} ${wheel_name}
      # Generate wheel
      ${Python3_EXECUTABLE} -m build \
        --verbose \
        --wheel \
        --outdir dist \
        --no-isolation \
        --skip-dependency-check \
        --config-setting=cmake.define.ITK_SOURCE_DIR:PATH=${source_path} \
        --config-setting=cmake.define.ITK_BINARY_DIR:PATH=${build_path} \
        --config-setting=cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
        --config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
        --config-setting=cmake.define.ITKPythonPackage_USE_TBB:BOOL=${use_tbb} \
        --config-setting=cmake.define.ITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON \
        --config-setting=cmake.define.ITKPythonPackage_WHEEL_NAME:STRING=${wheel_name} \
        --config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        --config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        ${CMAKE_OPTIONS//'-D'/'--config-setting=cmake.define.'} \
        ${CMAKE_COMPILER_ARGS//'-D'/'--config-setting=cmake.define.'} \
        . \
      || exit 1
    done

    # Remove unnecessary files for building against ITK
    find ${build_path} -name '*.cpp' -delete -o -name '*.xml' -delete
    rm -rf ${build_path}/Wrapping/Generators/castxml*
    find ${build_path} -name '*.o' -delete
done

if [[ $(arch) != "arm64" ]]; then
  for wheel in dist/itk_*.whl; do
    echo "Delocating $wheel"
    ${DELOCATE_LISTDEPS} $wheel # lists library dependencies
    ${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
  done
fi

for VENV in "${VENVS[@]}"; do
  ${VENV}/bin/pip install numpy
  ${VENV}/bin/pip install itk --no-cache-dir --no-index -f ${script_dir}/../dist
  (cd $HOME && ${VENV}/bin/python -c 'import itk;')
  (cd $HOME && ${VENV}/bin/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
  (cd $HOME && ${VENV}/bin/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
  (cd $HOME && ${VENV}/bin/python ${script_dir}/../docs/code/test.py )
done
