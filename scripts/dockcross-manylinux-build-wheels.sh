#!/bin/bash
# Run this script to build the ITK Python wheel packages for Linux.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/dockcross-manylinux-build-wheels.sh cp310
#
# A specialized manylinux image and tag can be used by setting
# MANYLINUX_VERSION and IMAGE_TAG
#
# For example,
#
#   export MANYLINUX_VERSION=_2_28
#   export IMAGE_TAG=20260203-3dfb3ff
#   scripts/dockcross-manylinux-build-module-wheels.sh cp310
#
script_dir=$(
  cd "$(dirname "$0")" || exit 1
  pwd
)
_ipp_dir=$(dirname "${script_dir}")

for cand in nerdctl docker podman; do
  if which "${cand}" >/dev/null; then
    export OCI_EXE=${OCI_EXE:="$cand"}
    break
  fi
done
echo "FOUND OCI_EXE=$(which "${OCI_EXE}")"

#For backwards compatibility when the ITK_GIT_TAG was required to match the ITK_PACKAGE_VERSION
ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION:="v6.0b02"}
ITK_GIT_TAG=${ITK_GIT_TAG:=${ITK_PACKAGE_VERSION}}
MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28}

# Default image tag differs by architecture:
#   x64     → dockcross/manylinux image (docker.io/dockcross)
#   aarch64 → pypa manylinux image      (quay.io/pypa, native ARM64 / QEMU on x64)
if [[ "${TARGET_ARCH}" == "aarch64" ]]; then
  IMAGE_TAG=${IMAGE_TAG:=2025.08.12-1}
  CONTAINER_SOURCE=${CONTAINER_SOURCE:="quay.io/pypa/manylinux${MANYLINUX_VERSION}_${TARGET_ARCH}:${IMAGE_TAG}"}
else
  # if x64 arch then default manylinux version is _2_28
  IMAGE_TAG=${IMAGE_TAG:=20260203-3dfb3ff}
  CONTAINER_SOURCE=${CONTAINER_SOURCE:="docker.io/dockcross/manylinux${MANYLINUX_VERSION}-${TARGET_ARCH}:${IMAGE_TAG}"}
fi
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG:=main}

# Required environment variables
required_vars=(
  ITK_GIT_TAG
  MANYLINUX_VERSION
  IMAGE_TAG
  TARGET_ARCH
  ITKPYTHONPACKAGE_ORG
  ITKPYTHONPACKAGE_TAG
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

mkdir -p "${_ipp_dir}/build"
cd "$(dirname "${_ipp_dir}")" || exit

# Build wheels in dockcross environment
CONTAINER_WORK_DIR=/work
CONTAINER_PACKAGE_BUILD_DIR=${CONTAINER_WORK_DIR}/ITKPythonPackage-build
CONTAINER_PACKAGE_SCRIPTS_DIR=${CONTAINER_WORK_DIR}/ITKPythonPackage
CONTAINER_ITK_SOURCE_DIR=${CONTAINER_PACKAGE_BUILD_DIR}/ITK

HOST_PACKAGE_SCRIPTS_DIR=${_ipp_dir}
HOST_PACKAGE_BUILD_DIR=$(dirname "${_ipp_dir}")/ITKPythonPackage-manylinux${MANYLINUX_VERSION}-build
mkdir -p "${HOST_PACKAGE_BUILD_DIR}"

DOCKER_ARGS="  -v ${HOST_PACKAGE_BUILD_DIR}:${CONTAINER_PACKAGE_BUILD_DIR} "
DOCKER_ARGS+=" -v ${HOST_PACKAGE_SCRIPTS_DIR}:${CONTAINER_PACKAGE_SCRIPTS_DIR} "
if [ "${ITK_SOURCE_DIR}" != "" ]; then
  DOCKER_ARGS+=" -v${ITK_SOURCE_DIR}:${CONTAINER_ITK_SOURCE_DIR} "
fi
DOCKER_ARGS+=" -e PYTHONUNBUFFERED=1 " # Turn off buffering of outputs in python

# To build tarballs in manylinux, use 'export BUILD_WHEELS_EXTRA_FLAGS=" --build-itk-tarball-cache "'
BUILD_WHEELS_EXTRA_FLAGS=${BUILD_WHEELS_EXTRA_FLAGS:=""} # No tarball by default

# If args are given, use them. Otherwise use default python environments
PY_ENVS=("${@:-py310 py311}")

if [[ "${TARGET_ARCH}" == "aarch64" ]]; then
  # aarch64: run the quay.io/pypa native image directly.
  # On ARM64 hosts (e.g. Apple Silicon) this runs natively.
  # On x64 hosts, first register QEMU binfmt emulation.
  if [[ ! ${NO_SUDO} ]]; then
    docker_prefix="sudo"
  fi
  # Only install QEMU binfmt emulation on non-ARM64 hosts; ARM64 hosts run natively
  if [[ "$(uname -m)" != "arm64" && "$(uname -m)" != "aarch64" ]]; then
    echo "Installing aarch64 architecture emulation tools to perform build for ARM platform"
    ${docker_prefix} "$OCI_EXE" run --privileged --rm tonistiigi/binfmt --install all
  fi

  # When building ITK wheels, module-related vars are empty
  cmd="${docker_prefix} \"$OCI_EXE\" run --rm \
      ${DOCKER_ARGS} \
      -e PY_ENVS=\"${PY_ENVS[*]}\" \
      -e ITK_GIT_TAG=\"${ITK_GIT_TAG}\" \
      -e ITK_PACKAGE_VERSION=\"${ITK_PACKAGE_VERSION:-}\" \
      -e MANYLINUX_VERSION=\"${MANYLINUX_VERSION}\" \
      -e IMAGE_TAG=\"${IMAGE_TAG}\" \
      -e TARGET_ARCH=\"${TARGET_ARCH}\" \
      -e ITKPYTHONPACKAGE_ORG=\"${ITKPYTHONPACKAGE_ORG}\" \
      -e ITKPYTHONPACKAGE_TAG=\"${ITKPYTHONPACKAGE_TAG}\" \
      -e BUILD_WHEELS_EXTRA_FLAGS=\"${BUILD_WHEELS_EXTRA_FLAGS}\" \
      ${CONTAINER_SOURCE} \
      /bin/bash -x ${CONTAINER_PACKAGE_SCRIPTS_DIR}/scripts/docker_build_environment_driver.sh"
else
  # x64: generate the dockcross runner script from the image, then invoke it.
  _local_dockercross_script=${_ipp_dir}/build/runner_dockcross-${MANYLINUX_VERSION}-${TARGET_ARCH}_${IMAGE_TAG}.sh
  "$OCI_EXE" run --rm "${CONTAINER_SOURCE}" >"${_local_dockercross_script}"
  chmod u+x "${_local_dockercross_script}"

  # When building ITK wheels, --module-source-dir, --module-dependancies-root-dir, and --itk-module-deps to be empty
  cmd="bash -x ${_local_dockercross_script} \
      -a \"$DOCKER_ARGS\" \
      /usr/bin/env \
      PY_ENVS=\"${PY_ENVS[*]}\" \
      ITK_GIT_TAG=\"${ITK_GIT_TAG}\" \
      ITK_PACKAGE_VERSION=\"${ITK_PACKAGE_VERSION:-}\" \
      MANYLINUX_VERSION=\"${MANYLINUX_VERSION}\" \
      IMAGE_TAG=\"${IMAGE_TAG}\" \
      TARGET_ARCH=\"${TARGET_ARCH}\" \
      ITKPYTHONPACKAGE_ORG=\"${ITKPYTHONPACKAGE_ORG}\" \
      ITKPYTHONPACKAGE_TAG=\"${ITKPYTHONPACKAGE_TAG}\" \
      BUILD_WHEELS_EXTRA_FLAGS=\"${BUILD_WHEELS_EXTRA_FLAGS}\" \
      /bin/bash -x ${CONTAINER_PACKAGE_SCRIPTS_DIR}/scripts/docker_build_environment_driver.sh"
fi

echo "RUNNING: $cmd"
eval "$cmd"
