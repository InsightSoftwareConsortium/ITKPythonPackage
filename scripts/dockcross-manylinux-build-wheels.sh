#!/bin/bash

# Pull dockcross manylinux images
docker pull dockcross/manylinux-x64
#docker pull dockcross/manylinux-x86

# Generate dockcross scripts
docker run dockcross/manylinux-x64 > /tmp/dockcross-manylinux-x64 && chmod u+x /tmp/dockcross-manylinux-x64
#docker run dockcross/manylinux-x86 > /tmp/dockcross-manylinux-x86 && chmod u+x /tmp/dockcross-manylinux-x86

script_dir="`cd $(dirname $0); pwd`"

# Build wheels
pushd $script_dir/..
mkdir -p dist
DOCKER_ARGS="-v $(pwd)/dist:/work/dist/"
/tmp/dockcross-manylinux-x64 -a "$DOCKER_ARGS" ./scripts/internal/manylinux-build-wheels.sh
#/tmp/dockcross-manylinux-x86 -a "$DOCKER_ARGS" ./scripts/internal/manylinux-build-wheels.sh
popd
