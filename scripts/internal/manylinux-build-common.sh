# Content common to manylinux-build-wheels.sh and
# manylinux-build-module-wheels.sh

set -e -x

script_dir=$(cd $(dirname $0) || exit 1; pwd)
# Workaround broken FindPython3 in CMake 3.17
if test -e /usr/share/cmake-3.17/Modules/FindPython/Support.cmake; then
  sudo cp ${script_dir}/Support.cmake /usr/share/cmake-3.17/Modules/FindPython/
fi

# Versions can be restricted by passing them in as arguments to the script
# For example,
# manylinux-build-wheels.sh cp39
if [[ $# -eq 0 ]]; then
  PYBIN=(/opt/python/*/bin)
  PYBINARIES=()
  for version in "${PYBIN[@]}"; do
    if [[ ${version} == *"cp37"* || ${version} == *"cp38"* || ${version} == *"cp39"* ]]; then
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
case $(uname -p) in
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
        die "Unknown architecture $(uname -p)"
        ;;
esac

# Install prerequirements
export PATH=/work/tools/doxygen-1.8.11/bin:$PATH
case $(uname -p) in
    i686)
        ARCH=x86
        ;;
    x86_64)
        if ! type doxygen > /dev/null 2>&1; then
          mkdir -p /work/tools
            pushd /work/tools > /dev/null 2>&1
            curl https://data.kitware.com/api/v1/file/5c0aa4b18d777f2179dd0a71/download -o doxygen-1.8.11.linux.bin.tar.gz
            tar -xvzf doxygen-1.8.11.linux.bin.tar.gz
          popd > /dev/null 2>&1
        fi
        ;;
    aarch64)
        ARCH=aarch64
        if ! type doxygen > /dev/null 2>&1; then
          mkdir -p /work/tools
            pushd /work/tools > /dev/null 2>&1
            curl https://data.kitware.com/api/v1/file/6086e4b02fa25629b93ac66e/download -o doxygen-1.8.11.linux.aarch64.bin.tar.gz
            tar -xvzf doxygen-1.8.11.linux.aarch64.bin.tar.gz
          popd > /dev/null 2>&1
        fi
        ;;
    *)
        die "Unknown architecture $(uname -p)"
        ;;
esac
if ! type ninja > /dev/null 2>&1; then
  if test ! -d ninja; then
    git clone git://github.com/ninja-build/ninja.git
  fi
  pushd ninja
  git checkout release
  cmake -Bbuild-cmake -H.
  cmake --build build-cmake
  cp build-cmake/ninja /usr/local/bin/
  popd
fi

echo "Building wheels for $ARCH"
