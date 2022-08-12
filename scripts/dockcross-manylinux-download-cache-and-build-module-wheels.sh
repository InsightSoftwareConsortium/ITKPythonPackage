#!/bin/bash

# This module should be pulled and run from an ITKModule root directory to generate the Linux python wheels of this module,
# it is used by the azure-pipeline.yml file contained in ITKModuleTemplate: https://github.com/InsightSoftwareConsortium/ITKModuleTemplate

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

# Packages distributed by github are in zstd format, so we need to download that binary to uncompress
if [[ ! -f zstd-1.2.0-linux.tar.gz ]]; then
  curl https://data.kitware.com/api/v1/file/592dd8068d777f16d01e1a92/download -o zstd-1.2.0-linux.tar.gz
  gunzip -d zstd-1.2.0-linux.tar.gz
  tar xf zstd-1.2.0-linux.tar
fi
if [[ ! -f ./zstd-1.2.0-linux/bin/unzstd ]]; then
  echo "ERROR: can not find required binary './zstd-1.2.0-linux/bin/unzstd'"
  exit 255
fi

TARBALL_NAME="ITKPythonBuilds-linux${TARBALL_SPECIALIZATION}.tar"

if [[ ! -f ${TARBALL_NAME}.zst ]]; then
  curl -L https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.2.0.post1}/${TARBALL_NAME}.zst -O
fi
if [[ ! -f ./${TARBALL_NAME}.zst ]]; then
  echo "ERROR: can not find required binary './${TARBALL_NAME}.zst'"
  exit 255
fi
./zstd-1.2.0-linux/bin/unzstd ./${TARBALL_NAME}.zst -o ${TARBALL_NAME}
if [ "$#" -lt 1 ]; then
  echo "Extracting all files";
  tar xf ${TARBALL_NAME}
else
  echo "Extracting files relevant for: $1";
  tar xf ${TARBALL_NAME} ITKPythonPackage/scripts/
  tar xf ${TARBALL_NAME} ITKPythonPackage/ITK-source/
  tar xf ${TARBALL_NAME} ITKPythonPackage/oneTBB-prefix/
  tar xf ${TARBALL_NAME} --wildcards ITKPythonPackage/ITK-$1*
fi
rm ${TARBALL_NAME}
if [[ ! -f ./ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh ]]; then
  echo "ERROR: can not find required binary './ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh'"
  exit 255
fi
cp -a ITKPythonPackage/oneTBB-prefix ./

set -- "${FORWARD_ARGS[@]}"; # Restore initial argument list
./ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh "$@"
