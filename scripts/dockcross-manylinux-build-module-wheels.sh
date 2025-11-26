#!/bin/bash

########################################################################
# Run this script to build the Python wheel packages for Linux for an ITK
# external module.
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
# See generate_build_environment.sh for description of environmental variable usage
# ENVIRONMENT VARIABLES: LD_LIBRARY_PATH, MANYLINUX_VERSION, TARGET_ARCH, IMAGE_TAG, ITK_MODULE_PREQ, ITK_MODULE_NO_CLEANUP, NO_SUDO
########################################################################

script_dir=$(cd $(dirname $0) || exit 1; pwd)
_ipp_dir=$(dirname ${script_dir})
package_env_file=${_ipp_dir}/build/package.env
if [ ! -f "${package_env_file}" ]; then
  ${_ipp_dir}/generate_build_environment.sh -o ${package_env_file}
fi
source "${package_env_file}"


if [[ -n ${ITK_MODULE_PREQ} ]]; then
  echo "Building module dependencies ${ITK_MODULE_PREQ}"
  source "${script_dir}/dockcross-manylinux-build-module-deps.sh"
fi

# NOTE: Directory must be in ${MODULE_ROOT_DIR}/ITKPythonPackage/scripts
#                                     ^        |        ^       |   ^
#                         HOST_MODULE_DIRECTORY|    _ipp_dir    |scripts_dir
HOST_MODULE_DIRECTORY=$(dirname ${_ipp_dir})

# Set up paths and variables for build
HOST_MODULE_TOOLS_DIR=${HOST_MODULE_DIRECTORY}/tools
mkdir -p  ${HOST_MODULE_TOOLS_DIR}
chmod 777 ${HOST_MODULE_TOOLS_DIR}

CONTAINER_WORK_DIR=/work
CONTAINER_PACKAGE_DIST=${CONTAINER_WORK_DIR}/dist
CONTAINER_PACKAGE_BUILD_DIR=${CONTAINER_WORK_DIR}/ITK-source
HOST_PACKAGE_BUILD_DIR=${_ipp_dir}/ITK-source
CONTAINER_ITK_SOURCE_DIR=${CONTAINER_PACKAGE_BUILD_DIR}/ITK
HOST_PACKAGE_DIST=${HOST_MODULE_DIRECTORY}/dist
mkdir -p ${HOST_PACKAGE_DIST}
HOST_PACKAGE_BUILD_DIR=${_ipp_dir}/ITK-source
mkdir -p ${HOST_PACKAGE_BUILD_DIR}
CONTAINER_IPP_DIR=/ITKPythonPackage
CONTAINER_TOOL_DIR=/tools
HOST_ONETBB_DIR=${_ipp_dir}/oneTBB-prefix
CONTAINER_ONETBB_DIR=/work/oneTBB-prefix

DOCKER_ARGS="-v ${HOST_MODULE_DIRECTORY}:${CONTAINER_WORK_DIR}"
DOCKER_ARGS+=" -v ${_ipp_dir}:${CONTAINER_IPP_DIR}"
DOCKER_ARGS+=" -v ${HOST_MODULE_TOOLS_DIR}:${CONTAINER_TOOL_DIR}"
DOCKER_ARGS+=" -v ${HOST_ONETBB_DIR}:${CONTAINER_ONETBB_DIR}"
DOCKER_ARGS+=" -v ${HOST_PACKAGE_BUILD_DIR}:${CONTAINER_PACKAGE_BUILD_DIR}"
DOCKER_ARGS+=" -v ${ITK_SOURCE_DIR}:${CONTAINER_ITK_SOURCE_DIR}"
DOCKER_ARGS+=" --env-file ${package_env_file}"
DOCKER_ARGS+=" -e MANYLINUX_VERSION"
DOCKER_ARGS+=" -e LD_LIBRARY_PATH"
# Mount any shared libraries
if [[ -n ${LD_LIBRARY_PATH} ]]; then
  for libpath in ${LD_LIBRARY_PATH//:/ }; do
          DOCKER_LIBRARY_PATH="/usr/lib64/$(basename -- ${libpath})"
          DOCKER_ARGS+=" -v ${libpath}:${DOCKER_LIBRARY_PATH}"
          if test -d ${libpath}; then
              DOCKER_LD_LIBRARY_PATH+="${DOCKER_LIBRARY_PATH}:${DOCKER_LD_LIBRARY_PATH}"
          fi
  done
fi
export LD_LIBRARY_PATH="${DOCKER_LD_LIBRARY_PATH}"

if [[ "${TARGET_ARCH}" = "aarch64" ]]; then
  echo "Install aarch64 architecture emulation tools to perform build for ARM platform"

  if [[ ! ${NO_SUDO} ]]; then
    docker_prefix="sudo"
  fi

  ${docker_prefix} $OCI_EXE run --env-file "${_ipp_dir}/build/package.env" \
                            --privileged --rm tonistiigi/binfmt --install all

  # Build wheels
  DOCKER_ARGS+=" --rm"
  ${docker_prefix} $OCI_EXE run --env-file "${_ipp_dir}/build/package.env" \
                                $DOCKER_ARGS ${CONTAINER_SOURCE} "/ITKPythonPackage/scripts/internal/manylinux-aarch64-build-module-wheels.sh" "$@"
else
  # Generate dockcross scripts
  _local_dockercross_script=${_ipp_dir}/build/runner_module_dockcross-${MANYLINUX_VERSION}-x64_${IMAGE_TAG}.sh
  $OCI_EXE run --env-file "${_ipp_dir}/build/package.env" \
               --rm ${CONTAINER_SOURCE} > ${_local_dockercross_script}
  chmod u+x ${_local_dockercross_script}

  # Build wheels
  ${_local_dockercross_script} \
    -a "$DOCKER_ARGS" \
    "/ITKPythonPackage/scripts/internal/manylinux-build-module-wheels.sh" "$@"
fi

if [[ -z ${ITK_MODULE_NO_CLEANUP} ]]; then
  source "${script_dir}/dockcross-manylinux-cleanup.sh"
fi
