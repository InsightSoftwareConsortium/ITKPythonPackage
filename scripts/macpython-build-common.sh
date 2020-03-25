# Content common to macpython-build-wheels.sh and
# macpython-build-module-wheels.sh

set -e -x

SCRIPT_DIR=$(cd $(dirname $0) || exit 1; pwd)

MACPYTHON_PY_PREFIX=/Library/Frameworks/Python.framework/Versions

# Versions can be restricted by passing them in as arguments to the script
# For example,
# macpython-build-wheels.sh 3.5
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
