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

# Verifies that unzstd binary is available to decompress ITK build archives.
unzstd_exe=`(which unzstd)`

if [[ -z ${unzstd_exe} ]]; then
  echo "ERROR: can not find required binary 'unzstd' "
  exit 255
fi

# Expect unzstd > v1.3.2, see discussion in `dockcross-manylinux-build-tarball.sh`
${unzstd_exe} --version

TARBALL_NAME="ITKPythonBuilds-linux${TARBALL_SPECIALIZATION}.tar"

if [[ ! -f ${TARBALL_NAME}.zst ]]; then
  curl -L https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.2.0.post1}/${TARBALL_NAME}.zst -O
fi
if [[ ! -f ./${TARBALL_NAME}.zst ]]; then
  echo "ERROR: can not find required binary './${TARBALL_NAME}.zst'"
  exit 255
fi
${unzstd_exe} --long=31 ./${TARBALL_NAME}.zst -o ${TARBALL_NAME}
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
