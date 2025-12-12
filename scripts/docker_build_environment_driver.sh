#!/bin/bash

CONTAINER_WORK_DIR=/work
cd ${CONTAINER_WORK_DIR}

CONTAINER_PACKAGE_DIST=${CONTAINER_WORK_DIR}/dist
CONTAINER_ENV_FILE=${CONTAINER_PACKAGE_DIST}/container_package.env

# Set BUILD_WHEELS_EXTRA_FLAGS="" to disable building the tarball or force cleanup
BUILD_WHEELS_EXTRA_FLAGS=${BUILD_WHEELS_EXTRA_FLAGS:=" --build-itk-tarball-cache --no-cleanup "}
PIXI_ENV=${PIXI_ENV:=manylinux228}
PY_ENVS=${PYENVS:=3.11}

# Use pixi to ensure all required tools are installed and
# visible in the PATH
export PIXI_HOME=${CONTAINER_WORK_DIR}/.pixi
export PATH=${PIXI_HOME}/bin:${PATH}
pixi install -e ${PIXI_ENV}

CONTAINER_ENV_FILE=${CONTAINER_PACKAGE_DIST}/container_package.env
echo DOXYGEN_EXECUTABLE=$(pixi run -e manylinux228 which doxygen) >> ${CONTAINER_ENV_FILE}
echo NINJA_EXECUTABLE=$(pixi run -e manylinux228 which ninja) >> ${CONTAINER_ENV_FILE}
echo CMAKE_EXECUTABLE=$(pixi run -e manylinux228 which cmake) >> ${CONTAINER_ENV_FILE}
# Set the path from within the container for the TBB_DIR
echo "TBB_DIR=${CONTAINER_WORK_DIR}/build/oneTBB-prefix/lib/cmake/TBB" >> ${CONTAINER_ENV_FILE}
echo "LD_LIBRARY_DIR=${CONTAINER_WORK_DIR}/build/oneTBB-prefix/lib" >> ${CONTAINER_ENV_FILE}

pixi run -e ${PIXI_ENV} python3.13 \
  ${CONTAINER_WORK_DIR}/scripts/build_wheels.py \
  --py-envs ${PY_ENVS} \
  ${BUILD_WHEELS_EXTRA_FLAGS} \
  --package-env-file ${CONTAINER_ENV_FILE}
