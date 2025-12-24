
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



#TODO: This needs updating to pass along values to
ITK_GIT_TAG=${ITK_GIT_TAG:="main"}
MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28}
IMAGE_TAG=${IMAGE_TAG:=20250913-6ea98ba}
TARGET_ARCH=${TARGET_ARCH:=x64}
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG:=main}

# Required environment variables
required_vars=(
  ITK_GIT_TAG
  MANYLINUX_VERSION
  IMAGE_TAG
  TARGET_ARCH
  ITKPYTHONPACKAGE_ORG
  ITKPYTHONPACKAGE_TAG
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

HOST_PACKAGE_DIST=${_ipp_dir}/dist
mkdir -p ${HOST_PACKAGE_DIST}



DOCKER_ARGS="  -v ${_ipp_dir}/dist:${CONTAINER_WORK_DIR}/dist/ "
if [ "${ITK_SOURCE_DIR}" -ne "" ]; then
  DOCKER_ARGS+=" -v${ITK_SOURCE_DIR}:${CONTAINER_ITK_SOURCE_DIR} "
fi
DOCKER_ARGS+=" -e PYTHONUNBUFFERED=1 " # Turn off buffering of outputs in python

BUILD_WHEELS_EXTRA_FLAGS=${BUILD_WHEELS_EXTRA_FLAGS:=" --build-itk-tarball-cache --no-cleanup "}

#If command line argument given, then use them
if [ $# -ge 1 ]; then
  PY_ENVS="$@"
else
  PY_ENVS="3.9 3.10 3.11"
fi

# When building ITK wheels, --module-source-dir, --module-dependancies-root-dir, and --itk-module-deps to be empty
cmd=$(echo bash -x ${_local_dockercross_script} \
  -a \"$DOCKER_ARGS\" \
   /usr/bin/env \
     PY_ENVS=\"${PY_ENVS}\" \
     ITK_GIT_TAG=\"${ITK_GIT_TAG}\" \
     MANYLINUX_VERSION=\"${MANYLINUX_VERSION}\" \
     IMAGE_TAG=\"${IMAGE_TAG}\" \
     TARGET_ARCH=\"${TARGET_ARCH}\" \
     ITKPYTHONPACKAGE_ORG=\"${ITKPYTHONPACKAGE_ORG}\" \
     ITKPYTHONPACKAGE_TAG=\"${ITKPYTHONPACKAGE_ORG}\" \
     /bin/bash -x ${CONTAINER_WORK_DIR}/scripts/docker_build_environment_driver.sh
)
echo "RUNNING: $cmd"
eval $cmd