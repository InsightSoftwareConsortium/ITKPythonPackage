# Content common to manylinux-build-wheels.sh and
# manylinux-build-module-wheels.sh

set -e -x

# Versions can be restricted by passing them in as arguments to the script
# For example,
# manylinux-build-wheels.sh cp27mu cp35
if [[ $# -eq 0 ]]; then
  PYBINARIES=(/opt/python/*/bin)
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

# Since the python interpreter exports its symbol (see [1]), python
# modules should not link against any python libraries.
# To ensure it is not the case, we configure the project using an empty
# file as python library.
#
# [1] "Note that libpythonX.Y.so.1 is not on the list of libraries that
# a manylinux1 extension is allowed to link to. Explicitly linking to
# libpythonX.Y.so.1 is unnecessary in almost all cases: the way ELF linking
# works, extension modules that are loaded into the interpreter automatically
# get access to all of the interpreter's symbols, regardless of whether or
# not the extension itself is explicitly linked against libpython. [...]"
#
# Source: https://www.python.org/dev/peps/pep-0513/#libpythonx-y-so-1
PYTHON_LIBRARY=$(cd $(dirname $0); pwd)/libpython-not-needed-symbols-exported-by-interpreter
touch ${PYTHON_LIBRARY}

