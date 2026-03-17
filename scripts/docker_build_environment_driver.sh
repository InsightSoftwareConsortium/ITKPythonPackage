#!/bin/bash

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
_missing_required=0
for v in "${required_vars[@]}"; do
  if [ -z "${!v:-}" ]; then
    _missing_required=1
    echo "ERROR: Required environment variable '$v' is not set or empty."
  fi
done
if [ "${_missing_required}" -ne 0 ]; then
  exit 1
fi
unset _missing_required

# -----------------------------------------------------------------------
# Set up paths
# These paths are inside the container

CONTAINER_WORK_DIR=/work
cd "${CONTAINER_WORK_DIR}" || exit
CONTAINER_PACKAGE_BUILD_DIR=${CONTAINER_WORK_DIR}/ITKPythonPackage-build
CONTAINER_PACKAGE_SCRIPTS_DIR=${CONTAINER_WORK_DIR}/ITKPythonPackage
CONTAINER_MODULE_SRC_DIRECTORY=${CONTAINER_WORK_DIR}/$(basename "${MODULE_SRC_DIRECTORY}")
CONTAINER_ITK_SOURCE_DIR=${CONTAINER_PACKAGE_BUILD_DIR}/ITK
BUILD_WHEELS_EXTRA_FLAGS=${BUILD_WHEELS_EXTRA_FLAGS:=""}
read -ra BUILD_WHEELS_EXTRA_FLAGS_ARRAY <<<"${BUILD_WHEELS_EXTRA_FLAGS}"

echo "BUILD FOR ${PY_ENVS}"
read -ra PY_ENVS_ARRAY <<<"${PY_ENVS}"

for py_indicator in "${PY_ENVS_ARRAY[@]}"; do
  py_squashed_numeric="${py_indicator//py/}"
  py_squashed_numeric="${py_squashed_numeric//cp/}"
  py_squashed_numeric="${py_squashed_numeric//./}"
  manylinux_vername="${MANYLINUX_VERSION//_/}"
  PIXI_ENV="manylinux${manylinux_vername}-py${py_squashed_numeric}"

  # Use pixi to ensure all required tools are installed and
  # visible in the PATH
  export PIXI_HOME=${CONTAINER_PACKAGE_SCRIPTS_DIR}/.pixi
  export PATH="${PIXI_HOME}/bin:${PATH}"
  python3.12 "${CONTAINER_PACKAGE_SCRIPTS_DIR}/scripts/install_pixi.py" --platform-env "${PIXI_ENV}"

  cd "${CONTAINER_PACKAGE_SCRIPTS_DIR}" || exit
  if [ -n "${MODULE_SRC_DIRECTORY}" ]; then
    pixi run -e "${PIXI_ENV}" python3 \
      "${CONTAINER_PACKAGE_SCRIPTS_DIR}/scripts/build_wheels.py" \
      --platform-env "${PIXI_ENV}" \
      "${BUILD_WHEELS_EXTRA_FLAGS_ARRAY[@]}" \
      --module-source-dir "${CONTAINER_MODULE_SRC_DIRECTORY}" \
      --module-dependencies-root-dir "${CONTAINER_MODULES_ROOT_DIRECTORY}" \
      --itk-module-deps "${ITK_MODULE_PREQ}" \
      --no-build-itk-tarball-cache \
      --build-dir-root "${CONTAINER_PACKAGE_BUILD_DIR}" \
      --itk-source-dir "${CONTAINER_ITK_SOURCE_DIR}" \
      --itk-git-tag "${ITK_GIT_TAG}" \
      --itk-package-version "${ITK_PACKAGE_VERSION:-}" \
      --manylinux-version "${MANYLINUX_VERSION}" \
      --no-use-sudo \
      --no-use-ccache \
      --skip-itk-build \
      --skip-itk-wheel-build
  else
    pixi run -e "${PIXI_ENV}" python3 \
      "${CONTAINER_PACKAGE_SCRIPTS_DIR}/scripts/build_wheels.py" \
      --platform-env "${PIXI_ENV}" \
      "${BUILD_WHEELS_EXTRA_FLAGS_ARRAY[@]}" \
      --build-itk-tarball-cache \
      --build-dir-root "${CONTAINER_PACKAGE_BUILD_DIR}" \
      --itk-source-dir "${CONTAINER_ITK_SOURCE_DIR}" \
      --itk-git-tag "${ITK_GIT_TAG}" \
      --itk-package-version "${ITK_PACKAGE_VERSION:-}" \
      --manylinux-version "${MANYLINUX_VERSION}" \
      --no-use-sudo \
      --no-use-ccache
  fi
  build_status=$?
  if [ "${build_status}" -ne 0 ]; then
    echo "ERROR: Build failed for ${py_indicator} with exit code ${build_status}"
    exit "${build_status}"
  fi

  echo "Successfully built wheel for ${py_indicator}"
done

echo ""
echo "========================================"
echo "All builds completed successfully!"
echo "========================================"
