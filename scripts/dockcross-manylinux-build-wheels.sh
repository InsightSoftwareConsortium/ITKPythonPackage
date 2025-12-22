
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
  # generate_build_environment.py respects environmental variables set by
  # ITKRemoteModuleBuildTestPackageAction/.github/workflows/build-test-package-python.yml
  ${_ipp_dir}/scripts/generate_build_environment.py -o ${package_env_file}
else
  # Re-use cached package_env_file
  ${_ipp_dir}/scripts/generate_build_environment.py -i ${package_env_file} -o ${package_env_file}
fi
source "${package_env_file}"

# Required environment variables
required_vars=(
  ITK_GIT_TAG
  ITKPYTHONPACKAGE_ORG
  ITKPYTHONPACKAGE_TAG
  IMAGE_TAG
  MANYLINUX_VERSION
  TARGET_ARCH
)

# Sanity Validation loop
for v in "${required_vars[@]}"; do
  if [ -z "${!v:-}" ]; then
    echo "ERROR: Required environment variable '$v' is not set or empty."
    exit 1
  fi
done

_local_dockercross_script=${_ipp_dir}/build/runner_dockcross-${MANYLINUX_VERSION}-x64_${IMAGE_TAG}.sh
# Generate dockcross scripts
$OCI_EXE run --env-file "${_ipp_dir}/build/package.env" \
             --rm docker.io/dockcross/manylinux${MANYLINUX_VERSION}-x64:${IMAGE_TAG} > ${_local_dockercross_script}
chmod u+x ${_local_dockercross_script}

# Build wheels in dockcross environment
CONTAINER_WORK_DIR=/work
CONTAINER_PACKAGE_DIST=${CONTAINER_WORK_DIR}/dist
CONTAINER_PACKAGE_BUILD_DIR=${CONTAINER_WORK_DIR}/ITK-source
CONTAINER_ITK_SOURCE_DIR=${CONTAINER_PACKAGE_BUILD_DIR}/ITK
CONTAINER_ENV_FILE=${CONTAINER_PACKAGE_DIST}/container_package.env

HOST_PACKAGE_DIST=${_ipp_dir}/dist
HOST_TO_CONTAINER_ENV_FILE=${HOST_PACKAGE_DIST}/container_package.env
mkdir -p ${HOST_PACKAGE_DIST}
#HOST_PACKAGE_BUILD_DIR=${_ipp_dir}/ITK-source_manylinux${MANYLINUX_VERSION}-x64_${IMAGE_TAG}
#mkdir -p ${HOST_PACKAGE_BUILD_DIR}

# Need to fixup path for container to find ITK, TODO: build_wheels.py should take in optional .env file
sed "s#ITK_SOURCE_DIR=.*#ITK_SOURCE_DIR=${CONTAINER_ITK_SOURCE_DIR}#g"  ${package_env_file} \
  | sed "s#DOXYGEN_EXECUTABLE=.*##g" - \
  | sed "s#NINJA_EXECUTABLE=.*##g"   - \
  | sed "s#CMAKE_EXECUTABLE=.*##g"   - > ${HOST_TO_CONTAINER_ENV_FILE}
mv ${package_env_file} ${package_env_file}_hidden

#If command line argument given, then use them
if [ $# -ge 1 ]; then
  PY_ENVS="$@"
else
  PY_ENVS="3.9 3.10 3.11"
fi

DOCKER_ARGS="  -v ${_ipp_dir}/dist:${CONTAINER_WORK_DIR}/dist/ "
DOCKER_ARGS+=" -v${ITK_SOURCE_DIR}:${CONTAINER_ITK_SOURCE_DIR} "
DOCKER_ARGS+=" --env-file ${HOST_TO_CONTAINER_ENV_FILE} "  # Configure container to start with correct environment variables
DOCKER_ARGS+=" -e PACKAGE_ENV_FILE=${CONTAINER_ENV_FILE} " # Choose the right env cache inside container (needed for subsequent scripts)
DOCKER_ARGS+=" -e PYTHONUNBUFFERED=1 " # Turn off buffering of outputs in python

BUILD_WHEELS_EXTRA_FLAGS=${BUILD_WHEELS_EXTRA_FLAGS:=" --build-itk-tarball-cache --no-cleanup "}
#BUILD_WHEELS_EXTRA_FLAGS=\"${BUILD_WHEELS_EXTRA_FLAGS}\" \
PIXI_ENV=${PIXI_ENV:=manylinux228}

# When building ITK wheels, --module-source-dir, --module-dependancies-root-dir, and --itk-module-deps to be empty
cmd=$(echo bash -x ${_local_dockercross_script} \
  -a \"$DOCKER_ARGS\" \
   /usr/bin/env \
     PIXI_ENV=\"${PIXI_ENV}\" \
     PY_ENVS=\"${PY_ENVS}\" \
     /bin/bash -x ${CONTAINER_WORK_DIR}/scripts/docker_build_environment_driver.sh
)
echo "RUNNING: $cmd"
eval $cmd

mv ${package_env_file}_hidden ${package_env_file}
