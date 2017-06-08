#!/bin/bash

# Run this script to build the ITK Python wheel packages for Linux.
#
# Versions can be restricted by passing them in as arguments to the script
# For example,
#
#   scripts/dockcross-manylinux-build-wheels.sh cp27mu cp35

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
pushd $script_dir/..
mkdir -p dist
DOCKER_ARGS="-v $(pwd)/dist:/work/dist/"
/tmp/dockcross-manylinux-x64 \
  -a "$DOCKER_ARGS" \
  ./scripts/internal/manylinux-build-wheels.sh "$@"
#/tmp/dockcross-manylinux-x86 \
#  -a "$DOCKER_ARGS" \
# ./scripts/internal/manylinux-build-wheels.sh "$@"
popd
