#!/bin/bash

# -----------------------------------------------------------------------
#
# Download ITK build cache and other requirements to prepare for generating Linux Python wheels of the given ITK module.
#
# Most ITK modules will download and call `dockcross-manylinux-download-cache-and-build-module-wheels.sh` which will
# subsequently fetch and run this script for getting build artifacts.
# ITK modules with tailored build processes may instead directly fetch and run this script as part of their own
# custom build workflow. Examples include ITK GPU-based modules that require additional system configuration
# steps not present in `dockcross-manylinux-download-cache-and-build-module-wheels.sh`.
#
# Exported variables used in this script:
# - ITK_PACKAGE_VERSION: Tag for ITKPythonBuilds build cache to use
#     Examples: "v5.3.0", "v5.2.1.post1"
#     See available tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags
# - MANYLINUX_VERSION: manylinux specialization used to build ITK for cache
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
  dockcross-manylinux-download-cache.sh
    [ -h | --help ]           show usage
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
    --) shift; break ;;
    *) echo "Unexpected option: $1.";
       usage; break ;;
  esac
done

# -----------------------------------------------------------------------
# Verify that unzstd binary is available to decompress ITK build archives.

unzstd_exe=`(which unzstd)`

if [[ -z ${unzstd_exe} ]]; then
  echo "ERROR: can not find required binary 'unzstd' "
  exit 255
fi

# Expect unzstd > v1.3.2, see discussion in `dockcross-manylinux-build-tarball.sh`
${unzstd_exe} --version

# -----------------------------------------------------------------------
# Fetch build archive

TARBALL_SPECIALIZATION="-manylinux${MANYLINUX_VERSION:=_2_28}"
TARBALL_NAME="ITKPythonBuilds-linux${TARBALL_SPECIALIZATION}.tar"

if [[ ! -f ${TARBALL_NAME}.zst ]]; then
  echo "Fetching https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.3.0}/${TARBALL_NAME}.zst"
  curl -L https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.3.0}/${TARBALL_NAME}.zst -O
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

ln -s ITKPythonPackage/oneTBB-prefix ./

# -----------------------------------------------------------------------
# Optional: Update build scripts
#
# ITKPythonBuilds archives include ITKPythonPackage build scripts from the
# time of build. Those scripts may be updated for any changes or fixes
# since the archives were generated.

if [[ -n ${ITKPYTHONPACKAGE_TAG} ]]; then
  echo "Updating build scripts to ${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}/ITKPythonPackage@${ITKPYTHONPACKAGE_TAG}"
  git clone "https://github.com/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git" "IPP-tmp"

  pushd IPP-tmp/
  git checkout "${ITKPYTHONPACKAGE_TAG}"
  git status
  popd
  
  rm -rf ITKPythonPackage/scripts/
  cp -r IPP-tmp/scripts ITKPythonPackage/
  cp IPP-tmp/requirements-dev.txt ITKPythonPackage/
  rm -rf IPP-tmp/
fi

if [[ ! -f ./ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh ]]; then
  echo "ERROR: can not find required binary './ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh'"
  exit 255
fi
