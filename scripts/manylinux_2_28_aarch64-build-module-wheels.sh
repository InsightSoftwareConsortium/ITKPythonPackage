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
# A specialized manylinux image and tag can be used by exporting to MANYLINUX_VERSION before
# running this script. Default is _2_28_aarch64.
#
# For example,
#
#   export MANYLINUX_VERSION=2014
#   export IMAGE_TAG=20221108-102ebcc
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39

MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28_aarch64}
IMAGE_TAG=${IMAGE_TAG:=latest}

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
docker run --rm -it $DOCKER_ARGS -v $(pwd):/work/ quay.io/pypa/manylinux${MANYLINUX_VERSION}:${IMAGE_TAG} "/ITKPythonPackage/scripts/internal/manylinux-aarch64-build-module-wheels.sh" "$@"
