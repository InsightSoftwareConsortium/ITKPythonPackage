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
# ENVIRONMENT VARIABLES
#
# These variables are set with the `export` bash command before calling the script.# 
# For example,
#
#   export MANYLINUX_VERSION="_2_28"
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39
# 
# `LD_LIBRARY_PATH`: Shared libraries to be included in the resulting wheel.
#   For instance, `export LD_LIBRARY_PATH="/path/to/OpenCL.so:/path/to/OpenCL.so.1.2"`
#
# `MANYLINUX_VERSION`: Specialized manylinux image to use for building. Default is _2_28.
#   See https://github.com/dockcross/dockcross for available versions and tags.
#   For instance, `export MANYLINUX_VERSION=2014`
#
# `TARGET_ARCH`: Target architecture for which wheels should be built.
#   For instance, `export MANYLINUX_VERSION=aarch64`
#
# `IMAGE_TAG`: Specialized manylinux image tag to use for building.
#   For instance, `export IMAGE_TAG=20221205-459c9f0`.
#   Tagged images are available at:
#   - https://github.com/dockcross/dockcross (x64 architecture)
#   - https://quay.io/organization/pypa (ARM architecture)
#
# `ITK_MODULE_PREQ`: Prerequisite ITK modules that must be built before the requested module.
#   See notes in `dockcross-manylinux-build-module-deps.sh`.
#
# `ITK_MODULE_NO_CLEANUP`: Option to skip cleanup steps.
#
# - `NO_SUDO`: Disable the use of superuser permissions for running docker.
#
########################################################################

# Handle case where the script directory is not the working directory
script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/dockcross-manylinux-set-vars.sh"
source "${script_dir}/oci_exe.sh"

oci_exe=$(ociExe)

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

  ${docker_prefix} $oci_exe run --privileged --rm tonistiigi/binfmt --install all

  # Build wheels
  DOCKER_ARGS+=" -v $(pwd):/work/ --rm"
  ${docker_prefix} $oci_exe run $DOCKER_ARGS ${CONTAINER_SOURCE} "/ITKPythonPackage/scripts/internal/manylinux-aarch64-build-module-wheels.sh" "$@"
else
  # Generate dockcross scripts
  $oci_exe run --rm ${CONTAINER_SOURCE} > /tmp/dockcross-manylinux-x64
  chmod u+x /tmp/dockcross-manylinux-x64

  # Build wheels
  /tmp/dockcross-manylinux-x64 \
    -a "$DOCKER_ARGS" \
    "/ITKPythonPackage/scripts/internal/manylinux-build-module-wheels.sh" "$@"
fi

if [[ -z ${ITK_MODULE_NO_CLEANUP} ]]; then
  source "${script_dir}/dockcross-manylinux-cleanup.sh"
fi
