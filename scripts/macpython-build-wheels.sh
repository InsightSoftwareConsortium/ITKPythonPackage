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

VENV="${VENVS[0]}"
Python3_EXECUTABLE=${VENV}/bin/python3
${Python3_EXECUTABLE} -m pip install --upgrade pip
${Python3_EXECUTABLE} -m pip install --no-cache-dir delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel

build_type="Release"

if [[ $(arch) == "arm64" ]]; then
  osx_arch="arm64"
else
  osx_arch="x86_64"
fi

# Build standalone project and populate archive cache
n_processors=$(sysctl -n hw.ncpu)
# So delocate can find the libs

# -----------------------------------------------------------------------
# Build required components (optional local ITK source, TBB builds) used to populate the archive cache
use_tbb="OFF"
if [[ "${use_tbb}" -eq "ON" ]]; then
  tbb_dir=$PWD/oneTBB-prefix/lib/cmake/TBB
  export DYLD_LIBRARY_PATH=${DYLD_LIBRARY_PATH}:${_ipp_dir}/oneTBB-prefix/lib
else
  tbb_dir="NOT-FOUND"
fi
IPP_SOURCE_DIR=${_ipp_dir}
IPP_SUPERBUILD_BINARY_DIR=${_ipp_dir}/ITK-source
mkdir -p ${IPP_SUPERBUILD_BINARY_DIR}
echo "CMAKE VERSION: $(${CMAKE_EXECUTABLE} --version)"
  cmd=$(echo ${CMAKE_EXECUTABLE} \
  -G \
  Ninja \
  -DITKPythonPackage_BUILD_PYTHON:BOOL=OFF \
  -DITKPythonPackage_USE_TBB:BOOL=${use_tbb} \
  -DCMAKE_BUILD_TYPE:STRING=${build_type} \
  -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
  -DITK_SOURCE_DIR=${ITK_SOURCE_DIR} \
  -DITK_GIT_TAG=${ITK_GIT_TAG} \
  -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
  -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
  ${CMAKE_COMPILER_ARGS} \
  -S \
  ${IPP_SOURCE_DIR} \
  -B \
  ${IPP_SUPERBUILD_BINARY_DIR}
  )
  echo "RUNNING: $cmd"
  eval $cmd
  ${NINJA_EXECUTABLE} -C ${IPP_SUPERBUILD_BINARY_DIR} -j$n_processors -l$n_processors
  echo "^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^"
  echo "================================================================"

# Compile wheels re-using standalone project and archive cache
for py_env in "${VENVS[@]}"; do
    py_mm=$(basename ${py_env})
    export Python3_EXECUTABLE=${py_env}/bin/python
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

    # Clean up previous invocations
    if [  "${ITK_MODULE_NO_CLEANUP:-0}" -eq 0  ]; then
      rm -rf ${build_path}
    fi

    echo "#"
    echo "# Build multiple ITK wheels"
    echo "#"

    # Build ITK python  -> build_wrapped_itk
    (
      mkdir -p ${build_path} \
      && cd ${build_path} \
      && echo "CMAKE VERSION: $(${CMAKE_EXECUTABLE} --version)" \
      && ${CMAKE_EXECUTABLE} \
        -G Ninja \
        -DCMAKE_MAKE_PROGRAM:FILEPATH=${NINJA_EXECUTABLE} \
        -DCMAKE_BUILD_TYPE:STRING=${build_type} \
        -DITK_SOURCE_DIR:PATH=${ITK_SOURCE_DIR} \
        -DITK_BINARY_DIR:PATH=${build_path} \
        -DBUILD_TESTING:BOOL=OFF \
        ${CMAKE_PLATFORM_FLAGS_NOT_YET_DEFINED} \
        -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
        -DCMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
        ${CMAKE_COMPILER_ARGS} \
        -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        -DITK_WRAP_unsigned_short:BOOL=ON \
        -DITK_WRAP_double:BOOL=ON \
        -DITK_WRAP_complex_double:BOOL=ON \
        -DITK_WRAP_IMAGE_DIMS:STRING="2;3;4" \
        -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel \
        -DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON \
        -DPY_SITE_PACKAGES_PATH:PATH="." \
        -DITK_LEGACY_SILENT:BOOL=ON \
        -DITK_WRAP_PYTHON:BOOL=ON \
        -DITK_WRAP_DOC:BOOL=ON \
        -DDOXYGEN_EXECUTABLE:FILEPATH=${DOXYGEN_EXECUTABLE} \
        -DModule_ITKTBB:BOOL=${use_tbb} \
        -DTBB_DIR:PATH=${tbb_dir} \
        ${CMAKE_OPTIONS} \
        -S ${ITK_SOURCE_DIR} \
        -B ${build_path}
      ${NINJA_EXECUTABLE} -C ${build_path} -j$n_processors -l$n_processors || exit 1
    )

    echo "BUILDING ITK Wheels"
    PYPROJECT_CONFIGURE="${script_dir}/pyproject_configure.py"
    wheel_names=$(cat ${script_dir}/WHEEL_NAMES.txt)
    for wheel_name in ${wheel_names}; do
      echo "==building ${wheel_name} in ${build_path} =="
      # Configure pyproject.toml
      ${Python3_EXECUTABLE} ${PYPROJECT_CONFIGURE} --env-file ${package_env_file} ${wheel_name}
      # Generate wheel
      ${Python3_EXECUTABLE} \
        -m build \
        --verbose \
        --wheel \
        --outdir ${IPP_SOURCE_DIR}/dist \
        --no-isolation \
        --skip-dependency-check \
        --config-setting=cmake.define.ITK_SOURCE_DIR:PATH=${ITK_SOURCE_DIR} \
        --config-setting=cmake.define.ITK_BINARY_DIR:PATH=${build_path} \
        --config-setting=cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET:STRING=${MACOSX_DEPLOYMENT_TARGET} \
        --config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING=${osx_arch} \
        --config-setting=cmake.define.ITKPythonPackage_USE_TBB:BOOL=${use_tbb} \
        --config-setting=cmake.define.ITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON \
        --config-setting=cmake.define.ITKPythonPackage_WHEEL_NAME:STRING=${wheel_name} \
        --config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        --config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        ${CMAKE_PLATFORM_FLAGS_NOT_YET_DEFINED} \
        ${CMAKE_OPTIONS//'-D'/'--config-setting=cmake.define.'} \
        ${CMAKE_COMPILER_ARGS//'-D'/'--config-setting=cmake.define.'} \
        ${IPP_SOURCE_DIR} \
      || exit 1
    done

    # Remove unnecessary files for building against ITK
    if [  "${ITK_MODULE_NO_CLEANUP:-0}" -eq 0  ]; then
      find ${build_path} -name '*.cpp' -delete -o -name '*.xml' -delete
      rm -rf ${build_path}/Wrapping/Generators/castxml*
      find ${build_path} -name '*.o' -delete
    fi
done

# ONLY ON LINUX sudo /opt/python/cp311-cp311/bin/pip3 install auditwheel wheel

if [[ $(arch) != "arm64" ]]; then
  for wheel in ${_ipp_dir}/dist/itk_*.whl; do
    echo "Delocating $wheel"
    ${DELOCATE_LISTDEPS} $wheel # lists library dependencies
    ${DELOCATE_WHEEL} $wheel # copies library dependencies into wheel
  done
fi

for py_env in "${VENVS[@]}"; do
  ${py_env}/bin/pip install numpy
  ${py_env}/bin/pip install --upgrade pip
  ${py_env}/bin/pip install itk --no-cache-dir --no-index -f ${_ipp_dir}/dist
  (cd $HOME && ${py_env}/bin/python -c 'import itk;')
  (cd $HOME && ${py_env}/bin/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
  (cd $HOME && ${py_env}/bin/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
  (cd $HOME && ${py_env}/bin/python ${_ipp_dir}/docs/code/test.py )
done

rm -f dist/numpy*.whl
