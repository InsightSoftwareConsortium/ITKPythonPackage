# Content common to macpython-build-wheels.sh and
# macpython-build-module-wheels.sh

set -e -x

if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    echo "ERROR: This script must be sourced with _ipp_dir predefined, not executed as a script."
    exit 1
fi

# ALWAYS_INTERNALLY_COMPUTED
MACPYTHON_PY_PREFIX=/Library/Frameworks/Python.framework/Versions
PYTHON_VERSIONS=""
CMAKE_OPTIONS=""

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

# -----------------------------------------------------------------------
# Remove previous virtualenv's
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
# Ensure that requirements are met
brew update
if ! type doxygen > /dev/null 2>&1; then
  brew info doxygen | grep --quiet 'Not installed' && brew install doxygen
fi
DOXYGEN_EXECUTABLE=${DOXYGEN_EXECUTABLE:=$(which doxygen)}
if ! type ninja > /dev/null 2>&1; then
  brew info ninja | grep --quiet 'Not installed' && brew install ninja
fi
NINJA_EXECUTABLE=${NINJA_EXECUTABLE:=$(which ninja)}
if ! type cmake > /dev/null 2>&1; then
  brew info cmake | grep --quiet 'Not installed' && brew install cmake
fi
CMAKE_EXECUTABLE=${CMAKE_EXECUTABLE:=$(which cmake)}
