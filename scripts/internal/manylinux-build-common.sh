# Content common to manylinux-build-wheels.sh and
# manylinux-build-module-wheels.sh

set -e -x


script_dir=$(cd $(dirname $0) || exit 1; pwd)
PATH=$(dirname ${DOXYGEN_EXECUTABLE}):$(dirname ${NINJA_EXECUTABLE}):$(dirname ${CMAKE_EXECUTABLE})$PATH
# Versions can be restricted by passing them in as arguments to the script
# For example,
# manylinux-build-wheels.sh cp39
if [[ $# -eq 0 ]]; then
  PYBIN=(/opt/python/*/bin)
  PYBINARIES=()
  for version in "${PYBIN[@]}"; do
    if [[ ${version} == *"cp39"* || ${version} == *"cp310"* || ${version} == *"cp311"* ]]; then
      PYBINARIES+=(${version})
    fi
  done
else
  PYBINARIES=()
  for version in "$@"; do
    PYBINARIES+=(/opt/python/*${version}*/bin)
  done
fi

# i686 or x86_64 ?
case $(uname -m) in
    i686)
        ARCH=x86
        ;;
    x86_64)
        ARCH=x64
        ;;
    aarch64)
        ARCH=aarch64
        ;;
    *)
        die "Unknown architecture $(uname -m)"
        ;;
esac

MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28}

# -----------------------------------------------------------------------
# Set cmake flags for compiler if CC or CXX are specified
CMAKE_COMPILER_ARGS=""
if [ ! -z "${CXX}" ]; then
  CMAKE_COMPILER_ARGS="-DCMAKE_CXX_COMPILER:STRING=${CXX}"
fi
if [ ! -z "${CC}" ]; then
  CMAKE_COMPILER_ARGS="${CMAKE_COMPILER_ARGS} -DCMAKE_C_COMPILER:STRING=${CC}"
fi

echo "Building wheels for $ARCH using manylinux${MANYLINUX_VERSION}"
