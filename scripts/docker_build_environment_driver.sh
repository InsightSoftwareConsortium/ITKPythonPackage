#!/bin/bash

CONTAINER_WORK_DIR=/work
cd ${CONTAINER_WORK_DIR}


# Required environment variables
required_vars=(
  ITK_GIT_TAG
  MANYLINUX_VERSION
  IMAGE_TAG
  TARGET_ARCH
  ITKPYTHONPACKAGE_ORG
  ITKPYTHONPACKAGE_TAG
  PY_ENVS
)
# Sanity Validation loop
for v in "${required_vars[@]}"; do
  if [ -z "${!v:-}" ]; then
    echo "ERROR: Required environment variable '$v' is not set or empty."
    exit 1
  fi
done

CONTAINER_PACKAGE_DIST=${CONTAINER_WORK_DIR}/dist

# Set BUILD_WHEELS_EXTRA_FLAGS="" to disable building the tarball or force cleanup
BUILD_WHEELS_EXTRA_FLAGS=${BUILD_WHEELS_EXTRA_FLAGS:=" --build-itk-tarball-cache "}

echo "BUILD FOR ${PY_ENVS}"

for pyver in ${PY_ENVS}; do
  py_vername=$(echo ${pyver} |sed 's/\.//g')
  manylinux_vername=$(echo ${MANYLINUX_VERSION} |sed 's/_//g')
  PIXI_ENV="manylinux${manylinux_vername}-py${py_vername}"

  # Use pixi to ensure all required tools are installed and
  # visible in the PATH
  export PIXI_HOME=${CONTAINER_WORK_DIR}/.pixi
  export PATH=${PIXI_HOME}/bin:${PATH}
  python3.12 ${CONTAINER_WORK_DIR}/scripts/install_pixi.py --platform-env ${PIXI_ENV}

  pixi run -e ${PIXI_ENV} python3 \
    ${CONTAINER_WORK_DIR}/scripts/build_wheels.py \
    --platform-env ${PIXI_ENV} \
    ${BUILD_WHEELS_EXTRA_FLAGS} \
   --build-dir-root ${CONTAINER_WORK_DIR} \
   --itk-git-tag ${ITK_GIT_TAG} \
   --manylinux-version ${MANYLINUX_VERSION} \

done
