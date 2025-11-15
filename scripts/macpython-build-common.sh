# Content common to macpython-build-wheels.sh and
# macpython-build-module-wheels.sh

set -e -x

SCRIPT_DIR=$(cd $(dirname $0) || exit 1; pwd)

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

# ALWAYS_INTERNALLY_COMPUTED
PYTHON_VERSIONS=""
CMAKE_OPTIONS=""
MACPYTHON_PY_PREFIX=""
PYBINARIES=""
SCRIPT_DIR=""

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
rm -rf ${SCRIPT_DIR}/../venvs
VENVS=()
mkdir -p ${SCRIPT_DIR}/../venvs
for PYBIN in "${PYBINARIES[@]}"; do
    if [[ $(basename $PYBIN) = "Current" ]]; then
      continue
    fi
    py_mm=$(basename ${PYBIN})
    VENV=${SCRIPT_DIR}/../venvs/${py_mm}
    VIRTUALENV_EXECUTABLE="${PYBIN}/bin/python3 -m venv"
    ${VIRTUALENV_EXECUTABLE} ${VENV}
    VENVS+=(${VENV})
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

# - `DOCKCROSS_ENV_REPORT`: A path to document the environment variables used in this build
DOCKCROSS_ENV_REPORT=${DOCKCROSS_ENV_REPORT:=$(mktemp /tmp/dockcross_${_local_script_name}.XXXXXX)}
cat > ${DOCKCROSS_ENV_REPORT} << OVERRIDE_ENV_SETTINGS
################################################
################################################
###  ITKPythonPackage Environment Variables  ###
###    (sourced from ${_local_script_name} ) ###

# Which ITK git tag/hash/branch to use as reference for building wheels/modules
# https://github.com/InsightSoftwareConsortium/ITK.git@\${ITK_PACKAGE_VERSION}
export ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION}

# Which script version to use in generating python packages
# https://github.com/InsightSoftwareConsortium/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git@\${ITKPYTHONPACKAGE_TAG}
export ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG}
export ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG}

# Which container to use for generating cross compiled packages
export oci_exe=${oci_exe}   # The container run environment
export MANYLINUX_VERSION=${MANYLINUX_VERSION}
export TARGET_ARCH=${TARGET_ARCH}
export IMAGE_TAG=${IMAGE_TAG}
# Almost never change MANYLINUX_IMAGE_NAME or CONTAINER_SOURCE directly
# export MANYLINUX_IMAGE_NAME="manylinux\${MANYLINUX_VERSION}-\${TARGET_ARCH}:\${IMAGE_TAG}"
# export CONTAINER_SOURCE=${CONTAINER_SOURCE}

# Environmental controls impacting dockcross-manylinux-build-module-wheels.sh
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}
export NO_SUDO=${NO_SUDO}
export ITK_MODULE_NO_CLEANUP=${ITK_MODULE_NO_CLEANUP}
export ITK_MODULE_PREQ=${ITK_MODULE_PREQ}

# Mac Specific environment settings
export DOXYGEN_EXECUTABLE=${DOXYGEN_EXECUTABLE}
export NINJA_EXECUTABLE=${NINJA_EXECUTABLE}
export CMAKE_EXECUTABLE=${CMAKE_EXECUTABLE}
# NOT OVERWRITABLE CMAKE_OPTIONS=${CMAKE_OPTIONS}
# NOT OVERWRITABLE PYTHON_VERSIONS=${PYTHON_VERSIONS}
# NOT OVERWRITABLE MACPYTHON_PY_PREFIX=${MACPYTHON_PY_PREFIX}
# NOT OVERWRITABLE PYBINARIES=${PYBINARIES}
# NOT OVERWRITEABLE SCRIPT_DIR=${SCRIPT_DIR}
# NOT OVERWRITEABLE VENVS=${VENVS}
################################################
################################################
OVERRIDE_ENV_SETTINGS
cat ${DOCKCROSS_ENV_REPORT}

