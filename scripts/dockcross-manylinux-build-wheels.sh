#!/bin/bash

# Run this script to build the ITK Python wheel packages for Linux.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/dockcross-manylinux-build-wheels.sh cp39
#
# A specialized manylinux image and tag can be used by exporting to
# MANYLINUX_VERSION and IMAGE_TAG before running this script.
# See https://github.com/dockcross/dockcross for available versions and tags.
#
# For example,
#
#   export MANYLINUX_VERSION=2014
#   export IMAGE_TAG=20221205-459c9f0
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39
#
script_dir=${script_dir:=$(cd $(dirname $0) || exit 1; pwd)}
_ipp_dir=$(dirname ${script_dir})
package_env_file=${_ipp_dir}/build/package.env
if [ ! -f "${_ipp_dir}/build/package.env" ]; then
  echo "MISSING: ${_ipp_dir}/build/package.env"
  echo "    RUN: ${_ipp_dir}/review generate_build_environment.sh"
  exit -1
fi
source "${_ipp_dir}/build/package.env"

# Generate dockcross scripts
$oci_exe run --env-file "${_ipp_dir}/build/package.env" \
             --rm docker.io/dockcross/manylinux${MANYLINUX_VERSION}-x64:${IMAGE_TAG} > /tmp/dockcross-manylinux-x64
chmod u+x /tmp/dockcross-manylinux-x64

# Build wheels
pushd $script_dir/..
mkdir -p dist
DOCKER_ARGS="-v $(pwd)/dist:/work/dist/"
DOCKER_ARGS+=" -e MANYLINUX_VERSION"
/tmp/dockcross-manylinux-x64 \
  -a "$DOCKER_ARGS" \
  ./scripts/internal/manylinux-build-wheels.sh "$@"
popd
