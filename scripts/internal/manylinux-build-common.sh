# Content common to manylinux-build-wheels.sh and
# manylinux-build-module-wheels.sh

set -e -x

# Versions can be restricted by passing them in as arguments to the script
# For example,
# manylinux-build-wheels.sh cp35
if [[ $# -eq 0 ]]; then
  PYBIN=(/opt/python/*/bin)
  PYBINARIES=()
  for version in "${PYBIN[@]}"; do
    if [[  ${version} == *"cp35"* || ${version} == *"cp36"* || ${version} == *"cp37"* || ${version} == *"cp38"*  ]]; then
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
