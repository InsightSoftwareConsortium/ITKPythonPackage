# Content common to macpython-build-wheels.sh and
# macpython-build-module-wheels.sh

set -e -x

if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    echo "ERROR: This script must be sourced with _ipp_dir predefined, not executed as a script."
    exit 1
fi

MACPYTHON_PY_PREFIX=/Library/Frameworks/Python.framework/Versions

# -----------------------------------------------------------------------
# Script argument parsing
#
usage()
{
  echo "Usage:
  macpython-build-common
    [ -h | --help ]           show usage
    [ -c | --cmake_options ]  space-separated string of CMake options to forward to the module (e.g. \"--config-setting=cmake.define.BUILD_TESTING=OFF\")
    [ -- python_versions ]        build wheel for a specific python version(s). (e.g. -- 3.9 3.10)"
  exit 2
}

PYTHON_VERSIONS=""
CMAKE_OPTIONS=""

while (( "$#" )); do
  case "$1" in
    -c|--cmake_options)
      CMAKE_OPTIONS="$2";
      shift 2;;
    -h|--help)
      usage;
      break;;
    --)
      shift;
      break;;
    *)
      # Parse any unrecognized arguments as python versions
      PYTHON_VERSIONS="${PYTHON_VERSIONS} $1";
      shift;;
  esac
done

# Parse all arguments after "--" as python versions
PYTHON_VERSIONS="${PYTHON_VERSIONS} $@"
# Trim whitespace
PYTHON_VERSIONS=$(xargs <<< "${PYTHON_VERSIONS}")

# Versions can be restricted by passing them in as arguments to the script
# For example,
# macpython-build-wheels.sh 3.9
if [[ -z "${PYTHON_VERSIONS}" ]]; then
  PYBINARIES=(${MACPYTHON_PY_PREFIX}/*)
else
  PYBINARIES=()
  for version in "$PYTHON_VERSIONS"; do
    PYBINARIES+=(${MACPYTHON_PY_PREFIX}/*${version}*)
  done
fi
#

# -----------------------------------------------------------------------
# Remove previous virtualenv's
if [[ ${ITK_MODULE_NO_CLEANUP} -eq 0 ]]; then
  rm -rf ${_ipp_dir}/venvs
fi
VENVS=()
mkdir -p ${_ipp_dir}/venvs
for PYBIN in "${PYBINARIES[@]}"; do
    if [[ $(basename $PYBIN) = "Current" ]]; then
      continue
    fi
    py_mm=$(basename ${PYBIN})
    _VENV_DIR=${_ipp_dir}/venvs/${py_mm}
    VIRTUALENV_EXECUTABLE="${PYBIN}/bin/python3 -m venv"
    ${VIRTUALENV_EXECUTABLE} ${_VENV_DIR}
    VENVS+=(${_VENV_DIR})
done

# -----------------------------------------------------------------------
# Set cmake flags for compiler if CC or CXX are specified
CMAKE_COMPILER_ARGS=""
if [ ! -z "${CXX}" ]; then
  CMAKE_COMPILER_ARGS="-DCMAKE_CXX_COMPILER:STRING=${CXX}"
fi
if [ ! -z "${CC}" ]; then
  CMAKE_COMPILER_ARGS="${CMAKE_COMPILER_ARGS} -DCMAKE_C_COMPILER:STRING=${CC}"
fi

if [[ ${USE_CCACHE} == "ON" ]];then
  # CCACHE_BASEDIR allows cache hits when only the base directory changes
  export CCACHE_BASEDIR=${ITK_SOURCE_DIR}
  CMAKE_COMPILER_ARGS="${CMAKE_COMPILER_ARGS} -DCMAKE_C_COMPILER_LAUNCHER=$(which ccache)  -DCMAKE_CXX_COMPILER_LAUNCHER=$(which ccache)"
fi
