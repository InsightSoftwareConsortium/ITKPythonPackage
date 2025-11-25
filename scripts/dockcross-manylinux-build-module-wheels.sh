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

# Set up paths and variables for build
mkdir -p $(pwd)/tools
chmod 777 $(pwd)/tools
mkdir -p dist
DOCKER_ARGS="-v $(pwd)/dist:/work/dist/ -v ${script_dir}/..:/ITKPythonPackage -v $(pwd)/tools:/tools"
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
  DOCKER_ARGS+=" -v $(pwd):/work/ --rm"
  ${docker_prefix} $OCI_EXE run --env-file "${_ipp_dir}/build/package.env" \
                                $DOCKER_ARGS ${CONTAINER_SOURCE} "/ITKPythonPackage/scripts/internal/manylinux-aarch64-build-module-wheels.sh" "$@"
else
  # Generate dockcross scripts
  $OCI_EXE run --env-file "${_ipp_dir}/build/package.env" \
               --rm ${CONTAINER_SOURCE} > /tmp/dockcross-manylinux-x64
  chmod u+x /tmp/dockcross-manylinux-x64

  # Build wheels
  /tmp/dockcross-manylinux-x64 \
    -a "$DOCKER_ARGS" \
    "/ITKPythonPackage/scripts/internal/manylinux-build-module-wheels.sh" "$@"
fi

if [[ -z ${ITK_MODULE_NO_CLEANUP} ]]; then
  source "${script_dir}/dockcross-manylinux-cleanup.sh"
fi
