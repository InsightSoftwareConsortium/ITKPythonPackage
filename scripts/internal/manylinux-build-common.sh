# Content common to manylinux-build-wheels.sh and
# manylinux-build-module-wheels.sh

set -e -x

script_dir=$(cd $(dirname $0) || exit 1; pwd)
# Workaround broken FindPython3 in CMake 3.17
sudo cp ${script_dir}/Support.cmake /usr/share/cmake-3.17/Modules/FindPython/

# Versions can be restricted by passing them in as arguments to the script
# For example,
# manylinux-build-wheels.sh cp39
if [[ $# -eq 0 ]]; then
  PYBIN=(/opt/python/*/bin)
  PYBINARIES=()
  for version in "${PYBIN[@]}"; do
    if [[ ${version} == *"cp36"* || ${version} == *"cp37"* || ${version} == *"cp38"* || ${version} == *"cp39"* ]]; then
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
    *)
        die "Unknown architecture $(uname -p)"
        ;;
esac

echo "Building wheels for $ARCH"
