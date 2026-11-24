#!/bin/bash

########################################################################
# Pull this script and run from an ITK external module root directory
# to generate the Linux Python wheels for the external module.
#
# ========================================================================
# PARAMETERS
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/dockcross-manylinux-build-module-wheels.sh cp311
#
# ===========================================
# ENVIRONMENT VARIABLES
#
# These variables are set with the `export` bash command before calling the script.
#
# `ITKPYTHONPACKAGE_ORG`: Github organization for fetching ITKPythonPackage build scripts.
#
# `ITKPYTHONPACKAGE_TAG`: ITKPythonPackage tag for fetching build scripts.
#
# Additional environment variables may be defined in accompanying build scripts.
#
########################################################################

download_script_dir=$(
  cd "$(dirname "$0")" || exit 1
  pwd
)
# if not specified, use the current directory for MODULE_SRC_DIRECTORY
MODULE_SRC_DIRECTORY=${MODULE_SRC_DIRECTORY:=${download_script_dir}}
# if not specified, keep module dependencies beside the extracted ITK cache
MODULE_DEPS_DIR=${MODULE_DEPS_DIR:=${download_script_dir}/MODULE_DEPENDENCIES}
mkdir -p "${MODULE_DEPS_DIR}"
# -----------------------------------------------------------------------
# Script argument parsing
#
usage() {
  echo "Usage:
  dockcross-manylinux-download-cache-and-build-module-wheels
    [ -h | --help ]           show usage
    [ -c | --cmake_options ]  space-delimited string containing CMake options to forward to the module (e.g. \"-DBUILD_TESTING=OFF\")
    [ -x | --exclude_libs ]   accepted for compatibility and ignored; nothing excludes libraries from the repair
    [ python_version ]        build wheel for a specific python version. (e.g. cp311)"
  exit 2
}

option_value() {
  if [ $# -lt 2 ]; then
    echo "Option $1 needs a value."
    usage
  fi
}

# Parsed by hand: BSD getopt on macOS has no long options. Options may follow
# the Python versions, as GNU getopt allowed.
python_versions=()
while [ $# -gt 0 ]; do
  case "$1" in
  -h | --help | -help)
    usage
    ;;
  -c | --cmake_options | -cmake_options)
    option_value "$@"
    export CMAKE_OPTIONS="$2"
    shift 2
    ;;
  --cmake_options=* | -cmake_options=*)
    export CMAKE_OPTIONS="${1#*=}"
    shift
    ;;
  -x | --exclude_libs | -exclude_libs)
    option_value "$@"
    echo "WARNING: --exclude_libs '$2' is ignored; no library is excluded from the wheel repair."
    shift 2
    ;;
  --exclude_libs=* | -exclude_libs=*)
    echo "WARNING: --exclude_libs '${1#*=}' is ignored; no library is excluded from the wheel repair."
    shift
    ;;
  --)
    shift
    python_versions+=("$@")
    break
    ;;
  -*)
    echo "Unexpected option: $1."
    usage
    ;;
  *)
    python_versions+=("$1")
    shift
    ;;
  esac
done
set -- "${python_versions[@]}"

# The ITKPythonBuilds cache layout must match these scripts, so there is no default release.
if [ -z "${ITK_PACKAGE_VERSION}" ]; then
  echo "ERROR: set ITK_PACKAGE_VERSION to the ITKPythonBuilds release tag to download."
  exit 1
fi
ITK_GIT_TAG=${ITK_GIT_TAG:=${ITK_PACKAGE_VERSION}}

# -----------------------------------------------------------------------
# Set default values
MANYLINUX_VERSION=${MANYLINUX_VERSION:-_2_28}
TARGET_ARCH=${TARGET_ARCH:-x64}

ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:-InsightSoftwareConsortium}
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG:-main}

# -----------------------------------------------------------------------
# Download and extract cache

echo "Fetching https://raw.githubusercontent.com/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage/${ITKPYTHONPACKAGE_TAG}/scripts/dockcross-manylinux-download-cache.sh"
curl -L "https://raw.githubusercontent.com/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage/${ITKPYTHONPACKAGE_TAG}/scripts/dockcross-manylinux-download-cache.sh" -O
chmod u+x dockcross-manylinux-download-cache.sh
_download_cmd="ITK_GIT_TAG=${ITK_GIT_TAG} \
    ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION} \
    ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG} \
    ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG} \
    MANYLINUX_VERSION=${MANYLINUX_VERSION} \
    TARGET_ARCH=${TARGET_ARCH} \
    bash -x \
    ${download_script_dir}/dockcross-manylinux-download-cache.sh $1"
echo "Running: ${_download_cmd}"
eval "${_download_cmd}"

#NOTE: in this scenario, untarred_ipp_dir is extracted from tarball
#      during ${download_script_dir}/dockcross-manylinux-download-cache.sh
untarred_ipp_dir=${download_script_dir}/ITKPythonPackage

ITK_SOURCE_DIR=${download_script_dir}/ITKPythonPackage-build/ITK

# -----------------------------------------------------------------------
# Build module wheels

echo "Building module wheels"

_bld_cmd="NO_SUDO=${NO_SUDO} \
    LD_LIBRARY_PATH=${LD_LIBRARY_PATH} \
    IMAGE_TAG=${IMAGE_TAG} \
    TARGET_ARCH=${TARGET_ARCH} \
    ITK_SOURCE_DIR=${ITK_SOURCE_DIR} \
    ITK_GIT_TAG=${ITK_GIT_TAG} \
    ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION} \
    ITK_MODULE_PREQ=${ITK_MODULE_PREQ} \
    ITK_MODULE_NO_CLEANUP=${ITK_MODULE_NO_CLEANUP} \
    MODULE_SRC_DIRECTORY=${MODULE_SRC_DIRECTORY} \
    MODULE_DEPS_DIR=${MODULE_DEPS_DIR} \
    MANYLINUX_VERSION=${MANYLINUX_VERSION} \
    ${untarred_ipp_dir}/scripts/dockcross-manylinux-build-module-wheels.sh $*"
echo "Running: ${_bld_cmd}"
eval "${_bld_cmd}"
