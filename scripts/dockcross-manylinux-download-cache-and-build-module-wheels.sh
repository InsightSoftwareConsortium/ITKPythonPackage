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
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39
#
# ===========================================
# ENVIRONMENT VARIABLES: ITKPYTHONPACKAGE_ORG, ITKPYTHONPACKAGE_TAG
########################################################################

script_dir=$(cd $(dirname $0) || exit 1; pwd)
_ipp_dir=$(dirname ${script_dir})
package_env_file=${_ipp_dir}/build/package.env
if [ ! -f "${package_env_file}" ]; then
  ${_ipp_dir}/generate_build_environment.sh -o ${package_env_file}
fi
source "${package_env_file}"

# -----------------------------------------------------------------------
# Script argument parsing
#
usage()
{
  echo "Usage:
  dockcross-manylinux-download-cache-and-build-module-wheels
    [ -h | --help ]           show usage
    [ -c | --cmake_options ]  space-delimited string containing CMake options to forward to the module (e.g. \"-DBUILD_TESTING=OFF\")
    [ -x | --exclude_libs ]   semicolon-delimited library names to exclude when repairing wheel (e.g. \"libcuda.so\")
    [ python_version ]        build wheel for a specific python version. (e.g. cp39)"
  exit 2
}

FORWARD_ARGS=("$@") # Store arguments to forward them later
PARSED_ARGS=$(getopt -a -n dockcross-manylinux-download-cache-and-build-module-wheels \
  -o hc:x: --long help,cmake_options:,exclude_libs: -- "$@")
eval set -- "$PARSED_ARGS"

while :
do
  case "$1" in
    -h | --help) usage; break ;;
    -c | --cmake_options) CMAKE_OPTIONS="$2" ; shift 2 ;;
    -x | --exclude_libs) EXCLUDE_LIBS="$2" ; shift 2 ;;
    --) shift; break ;;
    *) echo "Unexpected option: $1.";
       usage; break ;;
  esac
done

# -----------------------------------------------------------------------
# Download and extract cache

echo "Fetching https://raw.githubusercontent.com/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage/${ITKPYTHONPACKAGE_TAG}/scripts/dockcross-manylinux-download-cache.sh"
curl -L https://raw.githubusercontent.com/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage/${ITKPYTHONPACKAGE_TAG}/scripts/dockcross-manylinux-download-cache.sh -O
chmod u+x dockcross-manylinux-download-cache.sh
./dockcross-manylinux-download-cache.sh $1

# -----------------------------------------------------------------------
# Build module wheels

echo "Building module wheels"
set -- "${FORWARD_ARGS[@]}"; # Restore initial argument list
./ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh "$@"
