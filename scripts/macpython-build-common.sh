# Content common to macpython-build-wheels.sh and
# macpython-build-module-wheels.sh

set -e -x

SCRIPT_DIR=$(cd $(dirname $(readlink -f "$0")) || exit 1; pwd)

MACPYTHON_PY_PREFIX=/Library/Frameworks/Python.framework/Versions

# Versions can be restricted by passing them in as arguments to the script
# For example,
# macpython-build-wheels.sh 2.7 3.5
if [[ $# -eq 0 ]]; then
  PYBINARIES=(${MACPYTHON_PY_PREFIX}/*)
else
  PYBINARIES=()
  for version in "$@"; do
    PYBINARIES+=(${MACPYTHON_PY_PREFIX}/*${version}*)
  done
fi

VENVS=()
mkdir -p ${SCRIPT_DIR}/../venvs
for PYBIN in "${PYBINARIES[@]}"; do
    if [[ $(basename $PYBIN) = "Current" ]]; then
      continue
    fi
    py_mm=$(basename ${PYBIN})
    VENV=${SCRIPT_DIR}/../venvs/${py_mm}
    VENVS+=(${VENV})
done

VENV="${VENVS[0]}"
PYTHON_EXECUTABLE=${VENV}/bin/python
$PYTHON_EXECUTABLE -m pip install --no-cache cmake
CMAKE_EXECUTABLE=${VENV}/bin/cmake
$PYTHON_EXECUTABLE -m pip install --no-cache ninja
NINJA_EXECUTABLE=${VENV}/bin/ninja
$PYTHON_EXECUTABLE -m pip install --no-cache delocate
DELOCATE_LISTDEPS=${VENV}/bin/delocate-listdeps
DELOCATE_WHEEL=${VENV}/bin/delocate-wheel


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
PYTHON_LIBRARY=$(cd $(dirname $0); pwd)/internal/manylinux-libpython-not-needed-symbols-exported-by-interpreter
touch ${PYTHON_LIBRARY}
