#!/bin/bash

# Run this script to build the ITK Python wheel packages for Linux.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/dockcross-manylinux-build-wheels.sh cp39
#
# A specialized manylinux image and tag can be used by setting
# MANYLINUX_VERSION and IMAGE_TAG in build/package.env before running this script.
#
# For example,
#   generate_build_environment.sh # creates default build/package.env
#   edit build/package.env with desired build elements
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39
#
script_dir=$(cd $(dirname $0) || exit 1; pwd)
_ipp_dir=$(dirname ${script_dir})
package_env_file=${_ipp_dir}/build/package.env
if [ ! -f "${package_env_file}" ]; then
  ${_ipp_dir}/generate_build_environment.sh -o ${package_env_file}
fi
source "${package_env_file}"

_local_dockercross_script=${_ipp_dir}/build/runner_dockcross-${MANYLINUX_VERSION}-x64_${IMAGE_TAG}.sh
# Generate dockcross scripts
$oci_exe run --env-file "${_ipp_dir}/build/package.env" \
             --rm docker.io/dockcross/manylinux${MANYLINUX_VERSION}-x64:${IMAGE_TAG} > ${_local_dockercross_script}
chmod u+x ${_local_dockercross_script}

# Build wheels in dockcross environment
pushd ${_ipp_dir} # Must run _local_dockercross_script from the root of the directory with 
                  # CMakeFile.txt to be processed by ./scripts/internal/manylinux-build-wheels.sh

  CONTAINER_WORK_DIR=/work
  CONTAINER_PACKAGE_DIST=${CONTAINER_WORK_DIR}/dist
  CONTAINER_PACKAGE_BUILD_DIR=${CONTAINER_WORK_DIR}/ITK-source
  CONTAINER_ITK_SOURCE_DIR=${CONTAINER_PACKAGE_BUILD_DIR}/ITK
  HOST_PACKAGE_DIST=${_ipp_dir}/dist
  mkdir -p ${HOST_PACKAGE_DIST}
  HOST_PACKAGE_BUILD_DIR=${_ipp_dir}/ITK-source
  mkdir -p ${HOST_PACKAGE_BUILD_DIR}

  DOCKER_ARGS="-v ${_ipp_dir}/dist:${CONTAINER_WORK_DIR}/dist/  -v${ITK_SOURCE_DIR}:${CONTAINER_ITK_SOURCE_DIR} --env-file ${package_env_file}"
  cmd=$(echo bash -x ${_local_dockercross_script} \
    -a \"$DOCKER_ARGS\" \
    ${CONTAINER_WORK_DIR}/scripts/internal/manylinux-build-wheels.sh "$@")
  echo "RUNNING: $cmd"
  eval $cmd
popd
