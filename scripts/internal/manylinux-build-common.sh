# Content common to manylinux-build-wheels.sh and
# manylinux-build-module-wheels.sh

set -e -x


script_dir=$(cd $(dirname $0) || exit 1; pwd)

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

# Install prerequirements
export PATH=/work/tools/doxygen-1.8.16/bin:$PATH
case $(uname -m) in
    i686)
        ARCH=x86
        ;;
    x86_64)
        ARCH=x64
        if ! type doxygen > /dev/null 2>&1; then
          mkdir -p /work/tools
            pushd /work/tools > /dev/null 2>&1
            curl https://data.kitware.com/api/v1/file/62c4d615bddec9d0c46cb705/download -o doxygen-1.8.16.linux.bin.tar.gz
            tar -xvzf doxygen-1.8.16.linux.bin.tar.gz
          popd > /dev/null 2>&1
        fi
        ;;
    aarch64)
        ARCH=aarch64
        if ! type doxygen > /dev/null 2>&1; then
          mkdir -p /work/tools
          pushd /work/tools > /dev/null 2>&1
            curl https://data.kitware.com/api/v1/file/62c4ed58bddec9d0c46f1388/download -o doxygen-1.8.16.linux.aarch64.bin.tar.gz
            tar -xvzf doxygen-1.8.16.linux.aarch64.bin.tar.gz
          popd > /dev/null 2>&1
        fi
        ;;
    *)
        die "Unknown architecture $(uname -m)"
        ;;
esac
if ! type ninja > /dev/null 2>&1; then
  if test ! -d ninja; then
    git clone https://github.com/ninja-build/ninja.git
  fi
  pushd ninja
  git checkout release
  cmake -Bbuild-cmake -H.
  cmake --build build-cmake
  sudo cp build-cmake/ninja /usr/local/bin/
  popd
fi

MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28}

echo "Building wheels for $ARCH using manylinux${MANYLINUX_VERSION}"
