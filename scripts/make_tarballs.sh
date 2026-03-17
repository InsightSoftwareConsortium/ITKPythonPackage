#!/usr/bin/env bash
# NOTES: Building tarballs requires specific pathing for supporting github CI
#        workflows

script_dir=$(
  cd "$(dirname "$0")" || exit 1
  pwd
)
_ipp_dir=$(dirname "${script_dir}")

# If args are given, use them. Otherwise use default python environments
pyenvs=("${@:-py310 py311}")

# Otherwise process mac and linux based on uname

# Need to explicitly request to  --build-itk-tarball-cache
BUILD_WHEELS_EXTRA_FLAGS=("--build-itk-tarball-cache")
if [ -z "${ITK_GIT_TAG}" ]; then
  DEFAULT_ITK_GIT_TAG=v6.0b02
  echo "============================================================================="
  echo "============================================================================="
  for _ in x x x x x x x x x x x x x x x x x x x x x x x x x x x x x; do
    echo "===== WARNING: ITK_GIT_TAG not set, so defaulting to ${DEFAULT_ITK_GIT_TAG}"
  done
  echo "============================================================================="
  echo "============================================================================="
fi
ITK_GIT_TAG=${ITK_GIT_TAG:=${DEFAULT_ITK_GIT_TAG}}

## --
#  --
#  --
#  --
# Short circuit builds to use dockcross if MANYLINUX_VERSION is requested
if [ -n "${MANYLINUX_VERSION}" ]; then
  BUILD_WHEELS_EXTRA_FLAGS="${BUILD_WHEELS_EXTRA_FLAGS[*]}" \
    ITK_GIT_TAG=${ITK_GIT_TAG} \
    MANYLINUX_VERSION=${MANYLINUX_VERSION} \
    bash "${_ipp_dir}/scripts/dockcross-manylinux-build-wheels.sh" \
    "${pyenvs[@]}"
  exit $?
fi

## --
#  --
#  --
#  --
case "$(uname -s)" in
Darwin)
  PLATFORM_PREFIX="macosx"
  DASHBOARD_BUILD_DIRECTORY=${DASHBOARD_BUILD_DIRECTORY:=/Users/svc-dashboard/D/P}
  ;;
Linux)
  PLATFORM_PREFIX="linux"
  DASHBOARD_BUILD_DIRECTORY=${DASHBOARD_BUILD_DIRECTORY:=/work}
  ;;
  #  POSIX build env NOT SUPPORTED for windows, Needs to be done in a .ps1 shell
  #  MINGW*|MSYS*|CYGWIN*)
  #    PLATFORM_PREFIX="windows"
  #    DASHBOARD_BUILD_DIRECTORY="C:\P"
  #    ;;
*)
  echo "Unsupported platform: $(uname -s)"
  exit 1
  ;;
esac

# Required environment variables
required_vars=(
  ITK_GIT_TAG
  PLATFORM_PREFIX
  DASHBOARD_BUILD_DIRECTORY

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

if [ ! -d "${DASHBOARD_BUILD_DIRECTORY}" ]; then
  # This is the expected directory for the cache, It may require creation with administrator credentials
  mkdir -p "${DASHBOARD_BUILD_DIRECTORY}"
fi
if [ "${script_dir}" != "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage/scripts" ]; then
  echo "ERROR: Github CI requires rigid directory structure, you may substitute the ITKPythonPackage organization if testing"
  echo "  RUN: cd ${DASHBOARD_BUILD_DIRECTORY}"
  echo "  RUN: git clone git@github.com:${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git ${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage"
  echo "  FOR DEVELOPMENT RUN: git checkout python_based_build_scripts"
  echo "  RUN: ${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage/scripts/make_tarballs.sh"
  exit 1
fi

export PIXI_HOME=${DASHBOARD_BUILD_DIRECTORY}/.pixi
if [ ! -f "${PIXI_HOME}/bin/pixi" ]; then
  #PIXI INSTALL
  if [ ! -f "${PIXI_HOME}/bin/pixi" ]; then
    curl -fsSL https://pixi.sh/install.sh | sh
    export PATH="${PIXI_HOME}/bin:$PATH"
  fi
fi

for pyenv in "${pyenvs[@]}"; do
  cd "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage" || exit
  "${PIXI_HOME}/bin/pixi" run -e "${PLATFORM_PREFIX}-${pyenv}" \
    python3 "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage/scripts/build_wheels.py" \
    --platform-env "${PLATFORM_PREFIX}-${pyenv}" \
    --build-dir-root "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage-build" \
    --itk-source-dir "${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage-build/ITK" \
    --itk-git-tag "${ITK_GIT_TAG}" \
    "${BUILD_WHEELS_EXTRA_FLAGS[@]}"
done
