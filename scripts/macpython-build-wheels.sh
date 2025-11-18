#!/usr/bin/env bash

# Run this script to build the ITK Python wheel packages for macOS.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/macpython-build-wheels.sh 3.9
#
# Shared libraries can be included in the wheel by exporting them to DYLD_LIBRARY_PATH in build/package.env
#
# These variables are set in common script:, CMAKE_EXECUTABLE, CMAKE_OPTIONS, MACPYTHON_PY_PREFIX, PYBINARIES, PYTHON_VERSIONS, NINJA_EXECUTABLE, VENVS=()
#
# For example,
#
#   generate_build_environment.sh # creates default build/package.env
#   edit build/package.env with desired build elements
#   scripts/macpython-build-module-wheels.sh 3.9
#

# -----------------------------------------------------------------------

_script_dir=${_script_dir:=$(cd $(dirname $0) || exit 1; pwd)}
_ipp_dir=$(dirname ${_script_dir})
package_env_file=${_ipp_dir}/build/package.env
if [ ! -f "${package_env_file}" ]; then
  echo "MISSING: ${package_env_file}"
  echo "    RUN: ${_ipp_dir}/generate_build_environment.sh.sh"
  exit 1
fi
source "${package_env_file}"

source "${_script_dir}/macpython-build-common.sh"

VENV="${VENVS[0]}"
Python3_EXECUTABLE=${VENV}/bin/python3
${Python3_EXECUTABLE} -m pip install --upgrade pip
${Python3_EXECUTABLE} -m pip install --no-cache-dir delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel

build_type="Release"
use_ccache=ON
if [[ ${use_ccache} == "ON" ]];then
  CCACHE_CONFIG_FLAGS=" -DCMAKE_C_COMPILER_LAUNCHER=$(which ccache)  -DCMAKE_CXX_COMPILER_LAUNCHER=$(which ccache)"
else
  CCACHE_CONFIG_FLAGS=""
fi
MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET:="15.0"}
SDKROOT=${SDKROOT:=$(xcrun --sdk macosx --show-sdk-path)}

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

# -----------------------------------------------------------------------
IPP_BUILD_DIR=${_ipp_dir}/ITK-source
mkdir -p ${IPP_BUILD_DIR}

if [ ! -d ${ITK_SOURCE_DIR} ]; then
  git clone https://github.com/InsightSoftwareConsortium/ITK.git ${ITK_SOURCE_DIR}
fi
pushd ${ITK_SOURCE_DIR} > /dev/null 2>&1
  git checkout ${ITK_GIT_TAG}
popd > /dev/null 2>&1

echo "CMAKE VERSION: $(${CMAKE_EXECUTABLE} --version)"
${CMAKE_EXECUTABLE} -DITKPythonPackage_BUILD_PYTHON:PATH=0 \
  -DITKPythonPackage_USE_TBB:BOOL=${use_tbb} \
  -G Ninja \
  -DCMAKE_BUILD_TYPE:STRING=${build_type} \
  -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
  -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
  -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
  -DCMAKE_OSX_SYSROOT:STRING="${SDKROOT}" \
  -DCMAKE_C_COMPILER=${CC} \
  -DCMAKE_CXX_COMPILER=${CXX} \
  ${CCACHE_CONFIG_FLAGS} \
  -DITK_SOURCE_DIR=${ITK_SOURCE_DIR} \
  -DITK_GIT_TAG:STRING=${ITK_GIT_TAG} \
  -DITK_PACKAGE_VERSION:STRING=${ITK_PACKAGE_VERSION} \
  -S ${_ipp_dir} \
  -B ${IPP_BUILD_DIR} \
  \
  && ${NINJA_EXECUTABLE} -C ${IPP_BUILD_DIR} -j$n_processors -l$n_processors

SINGLE_WHEEL=0

# Compile wheels re-using standalone project and archive cache
for VENV in "${VENVS[@]}"; do
    py_mm=$(basename ${VENV})
    export Python3_EXECUTABLE=${VENV}/bin/python
    Python3_INCLUDE_DIR=$( find -L ${MACPYTHON_PY_PREFIX}/${py_mm}/include -name Python.h -exec dirname {} \; )

    echo ""
    echo "Python3_EXECUTABLE:${Python3_EXECUTABLE}"
    echo "Python3_INCLUDE_DIR:${Python3_INCLUDE_DIR}"

    ${Python3_EXECUTABLE} -m pip install --upgrade -r ${_ipp_dir}/requirements-dev.txt

    if [[ $(arch) == "arm64" ]]; then
      plat_name="macosx-${MACOSX_DEPLOYMENT_TARGET}-arm64"
      build_path="${_ipp_dir}/ITK-${py_mm}-macosx_arm64"
    else
      plat_name="macosx-${MACOSX_DEPLOYMENT_TARGET}-x86_64"
      build_path="${_ipp_dir}/ITK-${py_mm}-macosx_x86_64"
    fi
    PYPROJECT_CONFIGURE="${_script_dir}/pyproject_configure.py"

    # Clean up previous invocations
    if [  "${ITK_MODULE_NO_CLEANUP:-0}" -eq 0  ]; then
      rm -rf ${build_path}
    fi

    if [[ ${SINGLE_WHEEL} == 1 ]]; then

      echo "#"
      echo "# Build single ITK wheel"
      echo "#"

      # Configure pyproject.toml
      ${Python3_EXECUTABLE} ${PYPROJECT_CONFIGURE} "itk"
      # Generate wheel
      ${Python3_EXECUTABLE} -m build \
        --verbose \
        --wheel \
        --outdir dist \
        --no-isolation \
        --skip-dependency-check \
        --config-setting=cmake.define.CMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
        --config-setting=cmake.define.ITK_SOURCE_DIR:PATH=${ITK_SOURCE_DIR} \
        --config-setting=cmake.define.ITK_BINARY_DIR:PATH=${build_path} \
        --config-setting=cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
        --config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
        --config-setting=cmake.define.CMAKE_OSX_SYSROOT:STRING=${SDKROOT} \
        --config-setting=cmake.define.CMAKE_CXX_COMPILER:STRING=${CXX} \
        --config-setting=cmake.define.CMAKE_C_COMPILER:STRING=${CC} \
        --config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        --config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        --config-setting=cmake.define.Module_ITKTBB:BOOL=${use_tbb} \
        --config-setting=cmake.define.TBB_DIR:PATH=${tbb_dir} \
        . \
        ${CMAKE_OPTIONS}

    else

      echo "#"
      echo "# Build multiple ITK wheels"
      echo "#"

      # Build ITK python
      (
        mkdir -p ${build_path} \
        && cd ${build_path} \
        && echo "CMAKE VERSION: $(cmake --version)" \
        && cmake \
          -DCMAKE_BUILD_TYPE:STRING=${build_type} \
          -DITK_SOURCE_DIR:PATH=${ITK_SOURCE_DIR} \
          -DITK_BINARY_DIR:PATH=${build_path} \
          -DBUILD_TESTING:BOOL=OFF \
          -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
          -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
          -DCMAKE_OSX_SYSROOT:STRING=${SDKROOT} \
          -DCMAKE_CXX_COMPILER:STRING=${CXX} \
          -DCMAKE_C_COMPILER:STRING=${CC} \
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
          -S ${ITK_SOURCE_DIR} \
          -B ${build_path} \
        && ninja -j$n_processors -l$n_processors \
        || exit 1
      )

      wheel_names=$(cat ${_script_dir}/WHEEL_NAMES.txt)
      for wheel_name in ${wheel_names}; do
        echo "==building ${wheel_name} in $(pwd)=="
        # Configure pyproject.toml
        ${Python3_EXECUTABLE} ${PYPROJECT_CONFIGURE} ${wheel_name}
        # Generate wheel
        ${Python3_EXECUTABLE} -m build \
          --verbose \
          --wheel \
          --outdir dist \
          --no-isolation \
          --skip-dependency-check \
          --config-setting=cmake.define.ITK_SOURCE_DIR:PATH=${ITK_SOURCE_DIR} \
          --config-setting=cmake.define.ITK_BINARY_DIR:PATH=${build_path} \
          --config-setting=cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
          --config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
          --config-setting=cmake.define.CMAKE_OSX_SYSROOT:STRING=${SDKROOT} \
          --config-setting=cmake.define.CMAKE_CXX_COMPILER:STRING=${CXX} \
          --config-setting=cmake.define.CMAKE_C_COMPILER:STRING=${CC} \
          --config-setting=cmake.define.ITKPythonPackage_USE_TBB:BOOL=${use_tbb} \
          --config-setting=cmake.define.ITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON \
          --config-setting=cmake.define.ITKPythonPackage_WHEEL_NAME:STRING=${wheel_name} \
          --config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
          --config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
          . \
          ${CMAKE_OPTIONS} \
        || exit 1
      done

    fi

    # Remove unnecessary files for building against ITK
    if [  "${ITK_MODULE_NO_CLEANUP:-0}" -eq 0  ]; then
      find ${build_path} -name '*.cpp' -delete -o -name '*.xml' -delete
      rm -rf ${build_path}/Wrapping/Generators/castxml*
      find ${build_path} -name '*.o' -delete
    fi
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
  ${VENV}/bin/pip install itk --no-cache-dir --no-index -f ${_ipp_dir}/dist
  (cd $HOME && ${VENV}/bin/python -c 'import itk;')
  (cd $HOME && ${VENV}/bin/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
  (cd $HOME && ${VENV}/bin/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
  (cd $HOME && ${VENV}/bin/python ${_ipp_dir}/docs/code/test.py )
done
