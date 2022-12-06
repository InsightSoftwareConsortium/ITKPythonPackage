#!/bin/bash

# Run this script to build the Python wheel packages for Linux for an ITK
# external module.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39
#
# Shared libraries can be included in the wheel by exporting them to LD_LIBRARY_PATH before
# running this script.
# 
# For example,
#
#   export LD_LIBRARY_PATH="/path/to/OpenCL.so:/path/to/OpenCL.so.1.2"
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39
#
# A specialized manylinux image and tag can be used by exporting
# MANYLINUX_VERSION and IMAGE_TAG before running this script.
# See https://github.com/dockcross/dockcross for available versions and tags.
#
# For example,
#
#   export MANYLINUX_VERSION=2014
#   export IMAGE_TAG=20221205-459c9f0
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39
#

MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28}
IMAGE_TAG=${IMAGE_TAG:=20221205-459c9f0}

# Generate dockcross scripts
docker run --rm dockcross/manylinux${MANYLINUX_VERSION}-x64:${IMAGE_TAG} > /tmp/dockcross-manylinux-x64
chmod u+x /tmp/dockcross-manylinux-x64

script_dir=$(cd $(dirname $0) || exit 1; pwd)

mkdir -p $(pwd)/tools
chmod 777 $(pwd)/tools
# Build wheels
mkdir -p dist
DOCKER_ARGS="-v $(pwd)/dist:/work/dist/ -v $script_dir/..:/ITKPythonPackage -v $(pwd)/tools:/tools"
DOCKER_ARGS+=" -e MANYLINUX_VERSION"
# Mount any shared libraries
if [[ -n ${LD_LIBRARY_PATH} ]]; then
  for libpath in ${LD_LIBRARY_PATH//:/ }; do
	  DOCKER_ARGS+=" -v ${libpath}:/usr/lib64/$(basename -- ${libpath})"
  done
fi

/tmp/dockcross-manylinux-x64 \
  -a "$DOCKER_ARGS" \
  "/ITKPythonPackage/scripts/internal/manylinux-build-module-wheels.sh" "$@"
