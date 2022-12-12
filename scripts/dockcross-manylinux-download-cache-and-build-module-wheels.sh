#!/bin/bash

# This module should be pulled and run from an ITKModule root directory to generate the Linux python wheels of this module,
# it is used by the azure-pipeline.yml file contained in ITKModuleTemplate: https://github.com/InsightSoftwareConsortium/ITKModuleTemplate
#
# Exported variables used in this script:
# - ITK_PACKAGE_VERSION: Tag for ITKPythonBuilds build archive to use
#     Examples: "v5.3.0", "v5.2.1.post1"
#     See available tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags
# - MANYLINUX_VERSION: manylinux specialization to use
#     Examples: "_2_28", "2014", "_2_28_aarch64"
#     See https://github.com/dockcross/dockcross
# - ITKPYTHONPACKAGE_TAG: Tag for ITKPythonPackage build scripts to use.
#     If ITKPYTHONPACKAGE_TAG is empty then the default scripts distributed
#     with the ITKPythonBuilds archive will be used.
# - ITKPYTHONPACKAGE_ORG: Github organization or user to use for ITKPythonPackage
#     build script source. Default is InsightSoftwareConsortium.
#     Ignored if ITKPYTHONPACKAGE_TAG is empty.
#

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

echo "Fetching https://raw.githubusercontent.com/${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}/ITKPythonPackage/${ITKPYTHONPACKAGE_TAG:=v5.3.0}/scripts/dockcross-manylinux-download-cache.sh"
curl -L https://raw.githubusercontent.com/${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}/ITKPythonPackage/${ITKPYTHONPACKAGE_TAG:=v5.3.0}/scripts/dockcross-manylinux-download-cache.sh -O
chmod u+x dockcross-manylinux-download-cache.sh
./dockcross-manylinux-download-cache.sh $1

# -----------------------------------------------------------------------
# Build module wheels

echo "Building module wheels"
set -- "${FORWARD_ARGS[@]}"; # Restore initial argument list
if [[ "${MANYLINUX_VERSION}" = "_2_28_aarch64" ]]; then
  ./ITKPythonPackage/scripts/manylinux_2_28_aarch64-build-module-wheels.sh "$@"
else
  ./ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh "$@"
fi
