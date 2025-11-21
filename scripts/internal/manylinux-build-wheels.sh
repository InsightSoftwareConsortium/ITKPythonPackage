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
# The specialized manylinux container version should be set prior to running this script.
# See https://github.com/dockcross/dockcross for available versions and tags.
#
# For example, `docker run -e <var>` can be used to set an environment variable when launching a container:
#
#   export MANYLINUX_VERSION=2014
#   docker run --rm dockcross/manylinux${MANYLINUX_VERSION}-x64:${IMAGE_TAG} > /tmp/dockcross-manylinux-x64
#   chmod u+x /tmp/dockcross-manylinux-x64
#   /tmp/dockcross-manylinux-x64 -e MANYLINUX_VERSION manylinux-build-module-wheels.sh cp39
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
tbb_dir=/work/oneTBB-prefix/lib/cmake/TBB
# So auditwheel can find the libs
sudo ldconfig
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/work/oneTBB-prefix/lib:/usr/lib:/usr/lib64

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
    PYPROJECT_CONFIGURE="${script_dir}/../pyproject_configure.py"

    # Clean up previous invocations
    # rm -rf ${build_path}

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
        -DCMAKE_CXX_COMPILER_TARGET:STRING=$(uname -m)-linux-gnu \
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
      # Configure pyproject.toml
      ${PYBIN}/python ${PYPROJECT_CONFIGURE} ${wheel_name}
      # Generate wheel
      ${PYBIN}/python -m build \
        --verbose \
        --wheel \
        --outdir dist \
        --no-isolation \
        --skip-dependency-check \
        --config-setting=cmake.define.ITK_SOURCE_DIR:PATH=${source_path} \
        --config-setting=cmake.define.ITK_BINARY_DIR:PATH=${build_path} \
        --config-setting=cmake.define.ITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON \
        --config-setting=cmake.define.ITKPythonPackage_WHEEL_NAME:STRING=${wheel_name} \
        --config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE} \
        --config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR} \
        --config-setting=cmake.define.CMAKE_CXX_FLAGS:STRING="${compile_flags}" \
        --config-setting=cmake.define.CMAKE_C_FLAGS:STRING="${compile_flags}" \
        . \
        || exit 1
    done

    # Remove unnecessary files for building against ITK
    find ${build_path} -name '*.cpp' -delete -o -name '*.xml' -delete
    rm -rf ${build_path}/Wrapping/Generators/castxml*
    find ${build_path} -name '*.o' -delete

done

sudo /opt/python/cp311-cp311/bin/pip3 install auditwheel wheel

if test "${ARCH}" == "x64"; then
  # This step will fixup the wheel switching from 'linux' to 'manylinux<version>' tag
  for whl in dist/itk_*linux_*.whl; do
      /opt/python/cp311-cp311/bin/auditwheel repair --plat manylinux${MANYLINUX_VERSION}_x86_64 ${whl} -w /work/dist/
  done
else
  for whl in dist/itk_*$(uname -m).whl; do
      /opt/python/cp311-cp311/bin/auditwheel repair ${whl} -w /work/dist/
  done
fi

# auditwheel does not process this "metawheel" correctly since it does not
# have any native SO's.
mkdir -p metawheel-dist
for whl in dist/itk-*linux_*.whl; do
  /opt/python/cp311-cp311/bin/wheel unpack --dest metawheel ${whl}
  manylinux_version=manylinux${MANYLINUX_VERSION}
  new_tag=$(basename ${whl/linux/${manylinux_version}} .whl)
  sed -i "s/Tag: .*/Tag: ${new_tag}/" metawheel/itk-*/itk*.dist-info/WHEEL
  /opt/python/cp311-cp311/bin/wheel pack --dest metawheel-dist metawheel/itk-*
  mv metawheel-dist/*.whl dist/${new_tag}.whl
  rm -rf metawheel
done
rm -rf metawheel-dist
rm dist/itk-*-linux_*.whl
rm dist/itk_*-linux_*.whl

# Install packages and test
for PYBIN in "${PYBINARIES[@]}"; do
    ${PYBIN}/pip install --user numpy
    ${PYBIN}/pip install --upgrade pip
    ${PYBIN}/pip install itk --user --no-cache-dir --no-index -f /work/dist
    (cd $HOME && ${PYBIN}/python -c 'from itk import ITKCommon;')
    (cd $HOME && ${PYBIN}/python -c 'import itk; image = itk.Image[itk.UC, 2].New()')
    (cd $HOME && ${PYBIN}/python -c 'import itkConfig; itkConfig.LazyLoading = False; import itk;')
    (cd $HOME && ${PYBIN}/python ${script_dir}/../../docs/code/test.py )
done

rm -f dist/numpy*.whl
