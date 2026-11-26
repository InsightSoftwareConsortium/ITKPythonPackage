#!/bin/bash

########################################################################
# Run this script to build the Python wheel packages for Linux for an ITK
# external module.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/dockcross-manylinux-build-module-wheels.sh cp311
#
# ===========================================
# ENVIRONMENT VARIABLES
#
# These variables are set with the `export` bash command before calling the script.#
# For example,
#
#   export MANYLINUX_VERSION="_2_28"
#   scripts/dockcross-manylinux-build-module-wheels.sh cp311
#
# `LD_LIBRARY_PATH`: Shared libraries to be included in the resulting wheel.
#   For instance, `export LD_LIBRARY_PATH="/path/to/OpenCL.so:/path/to/OpenCL.so.1.2"`
#
# `MANYLINUX_VERSION`: Specialized manylinux image to use for building. Default is _2_28.
#   See https://github.com/dockcross/dockcross for available versions and tags.
#   For instance, `export MANYLINUX_VERSION=_2_28`
#
# `TARGET_ARCH`: Target architecture for which wheels should be built.
#   For instance, `export MANYLINUX_VERSION=aarch64`
#
# `IMAGE_TAG`: Specialized manylinux image tag to use for building.
#   For instance, `export IMAGE_TAG=2025.08.12-1`.
#   Tagged images are available at:
#   - https://github.com/dockcross/dockcross (x64 architecture)
#   - https://quay.io/organization/pypa (ARM architecture)
#
# `ITK_MODULE_PREQ`: Prerequisite ITK modules that must be built before the requested module.
#   Colon-delimited, for example `<org>/<repo>@<tag>:<org>/<repo>@<tag>`.
#
# `ITK_MODULE_NO_CLEANUP`: Option to skip cleanup steps.
#
# - `NO_SUDO`: Disable the use of superuser permissions for running docker.
#
# DIRECTORY STRUCTURE (expected):
#   ${IPP_DIR}/                              <- ITKPythonPackage
#   ${BUILD_DIR}/                            <- ITKPythonPackage-build (extracted cache)
#   ${MODULE_SOURCE_DIR}/                    <- Module source (current directory)
########################################################################

script_dir=$(
  cd "$(dirname "$0")" || exit 1
  pwd
)
_ipp_dir=$(dirname "${script_dir}")

# -----------------------------------------------------------------------
# Find container runtime
for cand in nerdctl docker podman; do
  if which "${cand}" >/dev/null 2>&1; then
    export OCI_EXE=${OCI_EXE:-"$cand"}
    break
  fi
done

if [ -z "${OCI_EXE}" ]; then
  echo "ERROR: No container runtime found. Please install docker, podman, or nerdctl."
  exit 1
fi
echo "Found OCI_EXE=$(which "${OCI_EXE}")"

# -----------------------------------------------------------------------
# Set default values
MANYLINUX_VERSION=${MANYLINUX_VERSION:-_2_28}
TARGET_ARCH=${TARGET_ARCH:-x64}
# Default image tag differs by architecture:
#   x64  → dockcross/manylinux image (docker.io/dockcross)
#   aarch64 → pypa manylinux image   (quay.io/pypa, native ARM64 / QEMU on x64)
if [[ "${TARGET_ARCH}" == "aarch64" ]]; then
  IMAGE_TAG=${IMAGE_TAG:-2025.08.12-1}
  CONTAINER_SOURCE=${CONTAINER_SOURCE:-"quay.io/pypa/manylinux${MANYLINUX_VERSION}_${TARGET_ARCH}:${IMAGE_TAG}"}
else
  # if x64 arch then default manylinux version is _2_28
  IMAGE_TAG=${IMAGE_TAG:=20260203-3dfb3ff}
  CONTAINER_SOURCE=${CONTAINER_SOURCE:-"docker.io/dockcross/manylinux${MANYLINUX_VERSION}-${TARGET_ARCH}:${IMAGE_TAG}"}
fi
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:-InsightSoftwareConsortium}
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG:-main}

# ITK_GIT_TAG defaults to the package version
ITK_GIT_TAG=${ITK_GIT_TAG:-${ITK_PACKAGE_VERSION}}

# Required environment variables
required_vars=(
  ITK_GIT_TAG
  MANYLINUX_VERSION
  IMAGE_TAG
  TARGET_ARCH
  ITKPYTHONPACKAGE_ORG
  ITKPYTHONPACKAGE_TAG
)
# shellcheck source=/dev/null
source "${script_dir}/require_env_vars.sh"
require_env_vars "${required_vars[@]}"

mkdir -p "${_ipp_dir}"/build
cd "$(dirname "${_ipp_dir}")" || exit

HOST_MODULE_DIRECTORY=${MODULE_SRC_DIRECTORY}

# Set up paths and variables for build
CONTAINER_WORK_DIR=/work
CONTAINER_PACKAGE_BUILD_DIR=${CONTAINER_WORK_DIR}/ITKPythonPackage-build
CONTAINER_PACKAGE_SCRIPTS_DIR=${CONTAINER_WORK_DIR}/ITKPythonPackage
HOST_PACKAGE_BUILD_DIR=$(dirname "${_ipp_dir}")/ITKPythonPackage-build
HOST_PACKAGE_SCRIPTS_DIR=${_ipp_dir}

CONTAINER_ITK_SOURCE_DIR=${CONTAINER_PACKAGE_BUILD_DIR}/ITK
HOST_PACKAGE_DIST=${HOST_MODULE_DIRECTORY}/dist
mkdir -p "${HOST_PACKAGE_DIST}"
CONTAINER_MODULE_DIR=${CONTAINER_WORK_DIR}/$(basename "${MODULE_SRC_DIRECTORY}")
CONTAINER_MODULE_DEPS_DIR=${CONTAINER_WORK_DIR}/$(basename "${MODULE_DEPS_DIR}")

# Build docker arguments
# Docker cannot combine --dns with --network=host; CONTAINER_DNS (space- or
# comma-separated) is for hosts whose containers cannot reach the default resolver.
if [ -n "${CONTAINER_DNS:-}" ]; then
  DOCKER_ARGS=""
  for _dns in ${CONTAINER_DNS//,/ }; do
    DOCKER_ARGS+=" --dns ${_dns} "
  done
else
  DOCKER_ARGS=" --network=host "
fi
DOCKER_ARGS+=" -v ${HOST_PACKAGE_BUILD_DIR}:${CONTAINER_PACKAGE_BUILD_DIR} "
DOCKER_ARGS+=" -v ${HOST_PACKAGE_SCRIPTS_DIR}:${CONTAINER_PACKAGE_SCRIPTS_DIR} "
DOCKER_ARGS+=" -v ${MODULE_SRC_DIRECTORY}:${CONTAINER_MODULE_DIR} "
DOCKER_ARGS+=" -v ${MODULE_DEPS_DIR}:${CONTAINER_MODULE_DEPS_DIR} "

if [ "${ITK_SOURCE_DIR}" != "" ]; then
  DOCKER_ARGS+=" -v ${ITK_SOURCE_DIR}:${CONTAINER_ITK_SOURCE_DIR} "
fi

# Environment variables for the container
DOCKER_ARGS+=" -e PYTHONUNBUFFERED=1 "
if [ -n "${SOURCE_DATE_EPOCH:-}" ]; then
  DOCKER_ARGS+=" -e SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} "
fi
# Build parallelism overrides read by scripts/build_jobs.py inside the container.
for _var in ITK_BUILD_JOBS ITK_BUILD_LOAD_LIMIT ITK_BUILD_LINK_JOBS; do
  if [ -n "${!_var:-}" ]; then
    DOCKER_ARGS+=" -e ${_var}=${!_var} "
  fi
done

# Mount shared libraries if LD_LIBRARY_PATH is set
if [[ -n ${LD_LIBRARY_PATH} ]]; then
  for libpath in ${LD_LIBRARY_PATH//:/ }; do
    DOCKER_LIBRARY_PATH="/usr/lib64/$(basename -- "${libpath}")"
    DOCKER_ARGS+=" -v ${libpath}:${DOCKER_LIBRARY_PATH}"
    if test -d "${libpath}"; then
      DOCKER_LD_LIBRARY_PATH+="${DOCKER_LIBRARY_PATH}:${DOCKER_LD_LIBRARY_PATH}"
    fi
  done
fi
export LD_LIBRARY_PATH="${DOCKER_LD_LIBRARY_PATH}"
# auditwheel in the container finds the libraries of mounted directories here.
if [[ -n ${LD_LIBRARY_PATH} ]]; then
  DOCKER_ARGS+=" -e LD_LIBRARY_PATH=${LD_LIBRARY_PATH} "
fi

# To build tarballs in manylinux, use 'export BUILD_WHEELS_EXTRA_FLAGS=" --build-itk-tarball-cache "'
BUILD_WHEELS_EXTRA_FLAGS=${BUILD_WHEELS_EXTRA_FLAGS:=""} # No tarball by default

PY_ENVS=("${@:-py311}")

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

  cmd="${docker_prefix} \"$OCI_EXE\" run --rm \
      ${DOCKER_ARGS} \
      -e PY_ENVS=\"${PY_ENVS[*]}\" \
      -e ITK_GIT_TAG=\"${ITK_GIT_TAG}\" \
      -e ITK_PACKAGE_VERSION=\"${ITK_PACKAGE_VERSION}\" \
      -e ITK_MODULE_PREQ=\"${ITK_MODULE_PREQ}\" \
      -e MODULE_SRC_DIRECTORY=\"${CONTAINER_MODULE_DIR}\" \
      -e MODULE_DEPS_DIR=\"${CONTAINER_MODULE_DEPS_DIR}\" \
      -e MANYLINUX_VERSION=\"${MANYLINUX_VERSION}\" \
      -e IMAGE_TAG=\"${IMAGE_TAG}\" \
      -e TARGET_ARCH=\"${TARGET_ARCH}\" \
      -e ITKPYTHONPACKAGE_ORG=\"${ITKPYTHONPACKAGE_ORG}\" \
      -e ITKPYTHONPACKAGE_TAG=\"${ITKPYTHONPACKAGE_TAG}\" \
      -e BUILD_WHEELS_EXTRA_FLAGS=\"${BUILD_WHEELS_EXTRA_FLAGS}\" \
      -e CMAKE_OPTIONS=\"${CMAKE_OPTIONS}\" \
      ${CONTAINER_SOURCE} \
      /bin/bash -x ${CONTAINER_PACKAGE_SCRIPTS_DIR}/scripts/docker_build_environment_driver.sh"
else
  # x64: generate the dockcross runner script from the image, then invoke it.
  _local_dockcross_script=${_ipp_dir}/build/runner_dockcross-${MANYLINUX_VERSION}-${TARGET_ARCH}_${IMAGE_TAG}.sh
  "$OCI_EXE" run --rm "${CONTAINER_SOURCE}" >"${_local_dockcross_script}"
  chmod u+x "${_local_dockcross_script}"

  # When building ITK remote wheels, --module-source-dir, --module-dependencies-root-dir, and --itk-module-deps should be present
  cmd="bash -x ${_local_dockcross_script} \
      -a \"$DOCKER_ARGS\" \
      /usr/bin/env \
      PY_ENVS=\"${PY_ENVS[*]}\" \
      ITK_GIT_TAG=\"${ITK_GIT_TAG}\" \
      ITK_PACKAGE_VERSION=\"${ITK_PACKAGE_VERSION}\" \
      ITK_MODULE_PREQ=\"${ITK_MODULE_PREQ}\" \
      MODULE_SRC_DIRECTORY=\"${CONTAINER_MODULE_DIR}\" \
      MODULE_DEPS_DIR=\"${CONTAINER_MODULE_DEPS_DIR}\" \
      MANYLINUX_VERSION=\"${MANYLINUX_VERSION}\" \
      IMAGE_TAG=\"${IMAGE_TAG}\" \
      TARGET_ARCH=\"${TARGET_ARCH}\" \
      ITKPYTHONPACKAGE_ORG=\"${ITKPYTHONPACKAGE_ORG}\" \
      ITKPYTHONPACKAGE_TAG=\"${ITKPYTHONPACKAGE_TAG}\" \
      BUILD_WHEELS_EXTRA_FLAGS=\"${BUILD_WHEELS_EXTRA_FLAGS}\" \
      CMAKE_OPTIONS=\"${CMAKE_OPTIONS}\" \
      /bin/bash -x ${CONTAINER_PACKAGE_SCRIPTS_DIR}/scripts/docker_build_environment_driver.sh"
fi

echo "RUNNING: $cmd"
eval "$cmd"
