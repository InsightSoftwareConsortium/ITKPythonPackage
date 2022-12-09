#!/bin/bash

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
#   export ITK_PACKAGE_VERSION="v5.3.0"
#   scripts/dockcross-manylinux-build-module-wheels.sh cp39
#
# `ITK_PACKAGE_VERSION`: ITKPythonBuilds archive tag to use for ITK build artifacts.
#   See https://github.com/InsightSoftwareConsortium/ITKPythonBuilds for available tags.
#   For instance, `export ITK_PACKAGE_VERSION=v5.3.0`.
# 
# `LD_LIBRARY_PATH`: Shared libraries to be included in the resulting wheel.
#   For instance, `export LD_LIBRARY_PATH="/path/to/OpenCL.so:/path/to/OpenCL.so.1.2"`
#
# `MANYLINUX_VERSION`: Specialized manylinux image to use for building. Default is _2_28.
#   See https://github.com/dockcross/dockcross for available versions and tags.
#   For instance, `export MANYLINUX_VERSION=2014`
#
# `IMAGE_TAG`: Specialized manylinux image tag to use for building.
#   For instance, `export IMAGE_TAG=20221205-459c9f0`
#
# `ITK_MODULE_PREQ`: Prerequisite ITK modules that must be built before the requested module.
#   Format is `<org_name>/<module_name>@<module_tag>:<org_name>/<module_name>@<module_tag>:...`.
#   For instance, `export ITK_MODULE_PREQ=InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0`
#
# `ITKPYTHONPACKAGE_ORG`: Github organization for fetching ITKPythonPackage build scripts.
#
# `ITKPYTHONPACKAGE_TAG`: ITKPythonPackage tag for fetching build scripts.
#
# `ITK_MODULE_NO_CLEANUP`: Option to skip cleanup steps.
#

# Handle case where the script directory is not the working directory
script_dir=$(cd $(dirname $0) || exit 1; pwd)
source "${script_dir}/dockcross-manylinux-set-vars.sh"

echo "ITK_MODULE_PREQ ${ITK_MODULE_PREQ}"
if [[ -n ${ITK_MODULE_PREQ} ]]; then
  source "${script_dir}/dockcross-manylinux-build-module-deps.sh"
fi

# Generate dockcross scripts
docker run --rm dockcross/manylinux${MANYLINUX_VERSION}-x64:${IMAGE_TAG} > /tmp/dockcross-manylinux-x64
chmod u+x /tmp/dockcross-manylinux-x64

mkdir -p $(pwd)/tools
chmod 777 $(pwd)/tools
# Build wheels
mkdir -p dist
DOCKER_ARGS="-v $(pwd)/dist:/work/dist/ -v ${script_dir}/..:/ITKPythonPackage -v $(pwd)/tools:/tools"
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

if [[ -z ${ITK_MODULE_NO_CLEANUP} ]]; then
  source "${script_dir}/dockcross-manylinux-cleanup.sh"
fi
