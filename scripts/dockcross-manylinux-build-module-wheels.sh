#!/bin/bash

# Run this script to build the Python wheel packages for Linux for an ITK
# external module.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/dockcross-manylinux-build-module-wheels.sh cp27mu cp35

# Pull dockcross manylinux images
docker pull dockcross/manylinux-x64
#docker pull dockcross/manylinux-x86

# Generate dockcross scripts
docker run dockcross/manylinux-x64 > /tmp/dockcross-manylinux-x64
chmod u+x /tmp/dockcross-manylinux-x64
#docker run dockcross/manylinux-x86 > /tmp/dockcross-manylinux-x86
#chmod u+x /tmp/dockcross-manylinux-x86

script_dir=$(cd $(dirname $0) || exit 1; pwd)

# Build wheels
mkdir -p dist
DOCKER_ARGS="-v $(pwd)/dist:/work/dist/ -v "$script_dir/..":/ITKPythonPackage"
/tmp/dockcross-manylinux-x64 \
  -a "$DOCKER_ARGS" \
  "/ITKPythonPackage/scripts/internal/manylinux-build-module-wheels.sh" "$@"
#/tmp/dockcross-manylinux-x86 \
#  -a "$DOCKER_ARGS" \
# "$script_dir/scripts/internal/manylinux-build-module-wheels.sh" "$@"
