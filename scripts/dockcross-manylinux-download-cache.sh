#!/bin/bash

########################################################################
# Download ITK build cache and other requirements to prepare for
# generating Linux Python wheels of the given ITK module.
#
# Most ITK modules will download and call `dockcross-manylinux-download-cache-and-build-module-wheels.sh` which will
# subsequently fetch and run this script for getting build artifacts.
# ITK modules with tailored build processes may instead directly fetch and run this script as part of their own
# custom build workflow. Examples include ITK GPU-based modules that require additional system configuration
# steps not present in `dockcross-manylinux-download-cache-and-build-module-wheels.sh`.
#
# ===========================================
# ENVIRONMENT VARIABLES: ITK_GIT_TAG, MANYLINUX_VERSION, ITKPYTHONPACKAGE_TAG, ITKPYTHONPACKAGE_ORG
########################################################################

# -----------------------------------------------------------------------
# Script argument parsing
#
usage() {
  echo "Usage:
  dockcross-manylinux-download-cache.sh
    [ -h | --help ]           show usage
    [ python_version ]        build wheel for a specific python version. (e.g. cp310)"
  exit 2
}

# Required environment variables
required_vars=(
  ITK_GIT_TAG
  ITK_PACKAGE_VERSION
  ITKPYTHONPACKAGE_ORG
  ITKPYTHONPACKAGE_TAG
  MANYLINUX_VERSION
  TARGET_ARCH
)

# Sanity Validation loop
_missing_required=0
for v in "${required_vars[@]}"; do
  if [ -z "${!v:-}" ]; then
    _missing_required=1
    echo "ERROR: Required environment variable '$v' is not set or empty."
  fi
done
if [ "${_missing_required}" -ne 0 ]; then
  exit 1
fi
unset _missing_required

PARSED_ARGS=$(getopt -a -n dockcross-manylinux-download-cache-and-build-module-wheels \
  -o hc:x: --long help,cmake_options:,exclude_libs: -- "$@")
eval set -- "$PARSED_ARGS"

while :; do
  case "$1" in
  -h | --help)
    usage
    ;;
  --)
    shift
    break
    ;;
  *)
    echo "Unexpected option: $1."
    usage
    ;;
  esac
done

# -----------------------------------------------------------------------
# Verify that unzstd binary is available to decompress ITK build archives.

unzstd_exe=$(which unzstd)

if [[ -z ${unzstd_exe} ]]; then
  echo "ERROR: can not find required binary 'unzstd' "
  exit 255
fi

# Expect unzstd > v1.3.2, see discussion in `dockcross-manylinux-build-tarball.sh`
${unzstd_exe} --version

# -----------------------------------------------------------------------
# Fetch build archive
TARBALL_NAME="ITKPythonBuilds-manylinux${MANYLINUX_VERSION}-${TARGET_ARCH}.tar"

if [[ ! -f ${TARBALL_NAME}.zst ]]; then
  echo "Local ITK cache tarball file not found..."
  echo "Fetching https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION}/${TARBALL_NAME}.zst"
  if ! curl -L "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION}/${TARBALL_NAME}.zst" -O; then
    echo "FAILED Download:"
    echo "curl -L https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION}/${TARBALL_NAME}.zst -O"
    exit 1
  fi
fi
if [[ ! -f ./${TARBALL_NAME}.zst ]]; then
  echo "ERROR: can not find required binary './${TARBALL_NAME}.zst'"
  exit 255
fi
"${unzstd_exe}" --long=31 "./${TARBALL_NAME}.zst" -o "${TARBALL_NAME}"

current_dir=$(pwd)
echo "Extracting all cache files from ${TARBALL_NAME} in ${current_dir}"
tar xf "${TARBALL_NAME}" --warning=no-unknown-keyword
rm "${TARBALL_NAME}"

# -----------------------------------------------------------------------
# Optional: Update build scripts
#
# ITKPythonBuilds archives include ITKPythonPackage build scripts from the
# time of build. Those scripts may be updated for any changes or fixes
# since the archives were generated.

if [[ -n ${ITKPYTHONPACKAGE_TAG} ]]; then
  # shellcheck disable=SC2153
  echo "Updating build scripts to ${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage@${ITKPYTHONPACKAGE_TAG}"
  git clone "https://github.com/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git" "${current_dir}/IPP-tmp"

  pushd "${current_dir}/IPP-tmp/" || exit
  git checkout "${ITKPYTHONPACKAGE_TAG}"
  git status
  popd || exit

  rm -rf "${current_dir}/ITKPythonPackage/scripts/"
  rsync -av "${current_dir}"/IPP-tmp/ "${current_dir}/ITKPythonPackage/"
  rm -rf "${current_dir}/IPP-tmp/"
fi

if [[ ! -f ${current_dir}/ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh ]]; then
  echo "ERROR: can not find required binary '${current_dir}/ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh'"
  exit 255
fi

echo "Finished fetching ITK build resources"
