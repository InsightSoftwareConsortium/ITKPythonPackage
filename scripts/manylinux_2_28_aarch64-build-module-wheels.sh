#!/bin/bash

# Run this script to build the Python wheel packages for Linux for an ITK
# external module.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/manylinux_2_28_aarch64-build-module-wheels.sh cp39
#
# Shared libraries can be included in the wheel by exporting them to LD_LIBRARY_PATH before
# running this script.
#
# For example,
#
#   export LD_LIBRARY_PATH="/path/to/OpenCL.so:/path/to/OpenCL.so.1.2"
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39
#

MANYLINUX_VERSION=_2_28
IMAGE_TAG=latest

script_dir=$(cd $(dirname $0) || exit 1; pwd)

mkdir -p $(pwd)/tools
chmod 777 $(pwd)/tools
# Build wheels
mkdir -p dist
DOCKER_ARGS="-v $(pwd)/dist:/work/dist/ -v $script_dir/..:/ITKPythonPackage -v $(pwd)/tools:/tools"
# Mount any shared libraries
if [[ -n ${LD_LIBRARY_PATH} ]]; then
  for libpath in ${LD_LIBRARY_PATH//:/ }; do
	  DOCKER_ARGS+=" -v ${libpath}:/usr/lib64/$(basename -- ${libpath})"
  done
fi

docker run --privileged --rm tonistiigi/binfmt --install all
docker run --rm $DOCKER_ARGS -v $(pwd):/work/ quay.io/pypa/manylinux${MANYLINUX_VERSION}_aarch64:${IMAGE_TAG} "/ITKPythonPackage/scripts/internal/manylinux-aarch64-build-module-wheels.sh" "$@"
