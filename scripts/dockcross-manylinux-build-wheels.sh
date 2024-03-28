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
script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/oci_exe.sh"

oci_exe=$(ociExe)

MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28}

if [[ ${MANYLINUX_VERSION} == _2_28 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=20240304-9e57d2b}
elif [[ ${MANYLINUX_VERSION} == 2014 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=20240304-9e57d2b}
else
  echo "Unknown manylinux version ${MANYLINUX_VERSION}"
  exit 1;
fi

# Generate dockcross scripts
$oci_exe run --rm docker.io/dockcross/manylinux${MANYLINUX_VERSION}-x64:${IMAGE_TAG} > /tmp/dockcross-manylinux-x64
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
