#!/bin/bash

########################################################################
# This module should be pulled and run from an ITK external module root directory
# to generate the Mac python wheels of this module.
#
# ========================================================================
# PARAMETERS
#
# Versions can be restricted by passing them in as arguments to the script.
# For example,
#
#   scripts/macpython-download-cache-and-build-module-wheels.sh 3.11
#
# Shared libraries can be included in the wheel by setting DYLD_LIBRARY_PATH before
# running this script.

# ===========================================
# ENVIRONMENT VARIABLES: ITK_GIT_TAG ITKPYTHONPACKAGE_ORG ITK_USE_LOCAL_PYTHON ITK_PACKAGE_VERSION
#
# These variables are set with the `export` bash command before calling the script.
# For example,
#   scripts/macpython-build-module-wheels.sh 3.10 3.11
#
########################################################################
DEFAULT_MODULE_DIRECTORY=$(
  cd "$(dirname "$0")" || exit 1
  pwd
)
# if not specified, use the current directory for MODULE_SRC_DIRECTORY
MODULE_SRC_DIRECTORY=${MODULE_SRC_DIRECTORY:=${DEFAULT_MODULE_DIRECTORY}}

usage() {
  echo "Usage:
  macpython-download-cache-and-build-module-wheels
    [ -h | --help ]           show usage
    [ -c | --cmake_options ]  space-delimited string containing CMake options to forward to the module (e.g. \"-DBUILD_TESTING=OFF\")
    [ python_version ]        build wheel for a specific python version. (e.g. 3.11)"
  exit 2
}

CMAKE_OPTIONS=""
while [ $# -gt 0 ]; do
  case "$1" in
  -h | --help) usage ;;
  -c | --cmake_options)
    CMAKE_OPTIONS="$2"
    shift 2
    ;;
  --)
    shift
    break
    ;;
  *)
    break
    ;;
  esac
done

if [ -z "${ITK_PACKAGE_VERSION}" ]; then
  echo "MUST SET ITK_PACKAGE_VERSION BEFORE RUNNING THIS SCRIPT"
  exit 1
fi

# For backwards compatibility when the ITK_GIT_TAG was required to match the ITK_PACKAGE_VERSION
ITK_GIT_TAG=${ITK_GIT_TAG:=${ITK_PACKAGE_VERSION}}

DASHBOARD_BUILD_DIRECTORY=${DASHBOARD_BUILD_DIRECTORY:=/Users/svc-dashboard/D/P}
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}
# Run build scripts
if [ -z "${NO_SUDO}" ] || [ "${NO_SUDO}" -ne 1 ]; then
  sudo_exec=sudo
fi
if [ ! -d "${DASHBOARD_BUILD_DIRECTORY}" ]; then
  ${sudo_exec} mkdir -p "${DASHBOARD_BUILD_DIRECTORY}" && ${sudo_exec} chown "$UID:$GID" "${DASHBOARD_BUILD_DIRECTORY}"
fi
cd "${DASHBOARD_BUILD_DIRECTORY}" || exit

# NOTE: download phase will install pixi in the DASHBOARD_BUILD_DIRECTORY (which is separate from the pixi
#       environment used by ITKPythonPackage).
export PIXI_HOME=${DASHBOARD_BUILD_DIRECTORY}/.pixi
if [ ! -f "${PIXI_HOME}/.pixi/bin/pixi" ]; then
  # Install pixi
  curl -fsSL https://pixi.sh/install.sh | sh
  # These are the tools needed for cross platform downloads of the ITK build caches stored in https://github.com/InsightSoftwareConsortium/ITKPythonBuilds
  pixi global install zstd
  pixi global install aria2
  pixi global install gnu-tar
  pixi global install git
  pixi global install rsync
fi
export PATH="${PIXI_HOME}/bin:$PATH"

tarball_arch="-$(arch)"
TARBALL_NAME="ITKPythonBuilds-macosx${tarball_arch}.tar"

if [[ ! -f ${TARBALL_NAME}.zst ]]; then
  echo "Local ITK cache tarball file not found..."
  # Fetch ITKPythonBuilds archive containing ITK build artifacts
  echo "Fetching https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION}/ITKPythonBuilds-macosx${tarball_arch}.tar.zst"
  if ! curl -L "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION}/ITKPythonBuilds-macosx${tarball_arch}.tar.zst" -O; then
    echo "FAILED Download:"
    echo "curl -L https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION}/${TARBALL_NAME}.zst -O"
    exit 1
  fi
fi

if [[ ! -f ./${TARBALL_NAME}.zst ]]; then
  echo "ERROR: can not find required binary './${TARBALL_NAME}.zst'"
  exit 255
fi

local_compress_tarball_name=${DASHBOARD_BUILD_DIRECTORY}/ITKPythonBuilds-macosx${tarball_arch}.tar.zst
if [[ ! -f ${local_compress_tarball_name} ]]; then
  aria2c -c --file-allocation=none -d "$(dirname "${local_compress_tarball_name}")" -o "$(basename "${local_compress_tarball_name}")" -s 10 -x 10 "https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION}/ITKPythonBuilds-macosx${tarball_arch}.tar.zst"
fi
local_tarball_name=${DASHBOARD_BUILD_DIRECTORY}/ITKPythonBuilds-macosx${tarball_arch}.tar
unzstd --long=31 "${local_compress_tarball_name}" -o "${local_tarball_name}"
# Find GNU tar (gtar from pixi or brew) for reliable extraction
if command -v gtar >/dev/null 2>&1; then
  TAR_CMD=gtar
  TAR_FLAGS=(--warning=no-unknown-keyword --checkpoint=10000 --checkpoint-action=dot)
elif tar --version 2>/dev/null | grep -q "GNU tar"; then
  TAR_CMD=tar
  TAR_FLAGS=(--warning=no-unknown-keyword --checkpoint=10000 --checkpoint-action=dot)
else
  TAR_CMD=tar
  TAR_FLAGS=()
fi
"${TAR_CMD}" xf "${local_tarball_name}" "${TAR_FLAGS[@]}"
rm "${local_tarball_name}"

# Optional: Update build scripts
if [[ -n ${ITKPYTHONPACKAGE_TAG} ]]; then
  echo "Updating build scripts to ${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage@${ITKPYTHONPACKAGE_TAG}"
  local_clone_ipp=${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage_${ITKPYTHONPACKAGE_TAG}
  if [ ! -d "${local_clone_ipp}/.git" ]; then
    git clone "https://github.com/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git" "${local_clone_ipp}"
  fi
  pushd "${local_clone_ipp}" || exit
  git checkout "${ITKPYTHONPACKAGE_TAG}"
  git reset "origin/${ITKPYTHONPACKAGE_TAG}" --hard
  git status
  popd || exit
  rsync -av "${local_clone_ipp}/" "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage/"
fi

echo "Building module wheels"
cd "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage" || exit
echo "$@"
for py_indicator in "$@"; do
  # The following line is to convert "py3.11|py311|cp311|3.11" -> py311 normalized form
  py_squashed_numeric=$(echo "${py_indicator}" | sed 's/py//g' | sed 's/cp//g' | sed 's/\.//g')
  pyenv=py${py_squashed_numeric}
  pixi run -e "macosx-${pyenv}" -- python \
    "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage/scripts/build_wheels.py" \
    --platform-env "macosx-${pyenv}" \
    --lib-paths '' '' \
    --module-source-dir "${MODULE_SRC_DIRECTORY}" \
    --module-dependencies-root-dir "${DASHBOARD_BUILD_DIRECTORY}/MODULE_DEPENDENCIES" \
    --itk-module-deps "${ITK_MODULE_PREQ}" \
    --no-build-itk-tarball-cache \
    --build-dir-root "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage-build" \
    --manylinux-version '' \
    --itk-git-tag "${ITK_GIT_TAG}" \
    --itk-source-dir "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage-build/ITK" \
    --itk-package-version "${ITK_PACKAGE_VERSION}" \
    --no-use-sudo \
    --no-use-ccache \
    --skip-itk-build \
    --skip-itk-wheel-build \
    ${CMAKE_OPTIONS:+-- ${CMAKE_OPTIONS}}
  #Let this be automatically selected --macosx-deployment-target 10.7 \
done
