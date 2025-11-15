# Content common to manylinux-build-wheels.sh and
# manylinux-build-module-wheels.sh

set -e -x

ARCH=""
PYBINARIES=""
Python3_LIBRARY=""

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
# First attempt to install doxygen from pixi
curl -fsSL https://pixi.sh/install.sh | bash
export PATH=~/.pixi/bin:$PATH
if ! type doxygen > /dev/null 2>&1; then
  pixi global install doxygen
fi

if ! type doxygen > /dev/null 2>&1; then
  case $(uname -m) in
    i686)
        ARCH=x86
        ;;
    x86_64)
        mkdir -p /work/tools
          pushd /work/tools > /dev/null 2>&1
          curl https://data.kitware.com/api/v1/file/62c4d615bddec9d0c46cb705/download -o doxygen-1.8.16.linux.bin.tar.gz
          tar -xvzf doxygen-1.8.16.linux.bin.tar.gz
          export PATH=/work/tools/doxygen-1.8.16/bin:$PATH
        popd > /dev/null 2>&1
        ;;
    aarch64)
        ARCH=aarch64
        mkdir -p /work/tools
          pushd /work/tools > /dev/null 2>&1
          curl https://data.kitware.com/api/v1/file/62c4ed58bddec9d0c46f1388/download -o doxygen-1.8.16.linux.aarch64.bin.tar.gz
          tar -xvzf doxygen-1.8.16.linux.aarch64.bin.tar.gz
          export PATH=/work/tools/doxygen-1.8.16/bin:$PATH
        popd > /dev/null 2>&1
        ;;
    *)
        die "Unknown architecture $(uname -m)"
        ;;
  esac
fi

if ! type ninja > /dev/null 2>&1; then
  pixi global install ninja
fi
if ! type ninja > /dev/null 2>&1; then
  if test ! -d ninja; then
    git clone https://github.com/ninja-build/ninja.git
  fi
  pushd ninja
  git checkout release
  cmake -Bbuild-cmake -H.
  cmake --build build-cmake
  cp build-cmake/ninja /usr/local/bin/
  popd
fi
