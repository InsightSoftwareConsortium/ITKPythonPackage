#!/bin/bash
# Build ITK + all remote module Python wheels.
# Usage: ./scripts/build-all-latest-wheels.sh [options]
#   --platform-env ENV    Pixi environment (default: linux-py311)
#   --itk-ref REF         ITK branch, tag, or commit hash (default: main)
#   --itk-repo URL        ITK git URL
#   --ipp-branch BRANCH   ITKPythonPackage branch (default: python-build-system)
#   --ipp-repo URL        ITKPythonPackage git URL
# Example:
#   ./scripts/build-all-latest-wheels.sh --itk-ref v6.0b02 --platform-env linux-py311
set -euo pipefail

# Defaults
PLATFORM_ENV="linux-py311"
ITK_REF="main"
ITK_REPO="https://github.com/InsightSoftwareConsortium/ITK.git"
IPP_REPO="https://github.com/BRAINSia/ITKPythonPackage.git"
IPP_BRANCH="python-build-system"

while [[ $# -gt 0 ]]; do
  case "$1" in
  --platform-env)
    PLATFORM_ENV="$2"
    shift 2
    ;;
  --itk-ref)
    ITK_REF="$2"
    shift 2
    ;;
  --itk-repo)
    ITK_REPO="$2"
    shift 2
    ;;
  --ipp-branch)
    IPP_BRANCH="$2"
    shift 2
    ;;
  --ipp-repo)
    IPP_REPO="$2"
    shift 2
    ;;
  *)
    echo "Unknown option: $1"
    exit 1
    ;;
  esac
done

TIMESTAMP=$(date +%Y%m%d%H%M%S)
WORKDIR="/tmp/${TIMESTAMP}_LatestITKPython"
DIST_DIR="${WORKDIR}/dist"

mkdir -p "${DIST_DIR}"
echo "=== Build directory: ${WORKDIR}"
echo "=== Platform: ${PLATFORM_ENV}"
echo "=== ITK ref: ${ITK_REF}"

# 1) Clone ITK
echo "=== Cloning ITK (${ITK_REF})..."
git clone "${ITK_REPO}" "${WORKDIR}/ITK"
git -C "${WORKDIR}/ITK" checkout "${ITK_REF}"

# 2) Clone ITKPythonPackage
echo "=== Cloning ITKPythonPackage (${IPP_BRANCH})..."
git clone --branch "${IPP_BRANCH}" "${IPP_REPO}" "${WORKDIR}/ITKPythonPackage"

# 3) Parse remote modules from ITK and clone each
echo "=== Cloning remote modules..."
MODULES_DIR="${WORKDIR}/modules"
mkdir -p "${MODULES_DIR}"
module_list=()

for rc in "${WORKDIR}"/ITK/Modules/Remote/*.remote.cmake; do
  name=$(basename "${rc}" .remote.cmake)
  repo=$(grep 'GIT_REPOSITORY' "${rc}" | sed 's/.*GIT_REPOSITORY *//;s/ *)//;s/[[:space:]]*$//')
  [ -z "${repo}" ] && continue

  echo "  Cloning ${name} from ${repo}..."
  if git clone --depth 1 "${repo}" "${MODULES_DIR}/${name}" 2>/dev/null; then
    # Only keep modules that have Python wrapping
    if [ -d "${MODULES_DIR}/${name}/wrapping" ] && [ -f "${MODULES_DIR}/${name}/pyproject.toml" ]; then
      module_list+=("${name}")
    else
      rm -rf "${MODULES_DIR:?}/${name}"
    fi
  else
    echo "  WARNING: Failed to clone ${name}, skipping"
  fi
done

echo "=== ${#module_list[@]} modules with Python wrapping"

# 4) Build ITK wheels
cd "${WORKDIR}/ITKPythonPackage"
echo "=== Building ITK Python wheels..."
pixi run -e "${PLATFORM_ENV}" -- python scripts/build_wheels.py \
  --platform-env "${PLATFORM_ENV}" \
  --itk-git-tag main \
  --itk-source-dir "${WORKDIR}/ITK" \
  --no-build-itk-tarball-cache \
  --no-use-sudo \
  --build-dir-root "${WORKDIR}/build"

# Copy ITK wheels to dist
cp "${WORKDIR}"/build/dist/*.whl "${DIST_DIR}/" 2>/dev/null || true

# 5) Build each remote module wheel
failed_modules=()
for name in "${module_list[@]}"; do
  echo "=== Building ${name}..."
  if pixi run -e "${PLATFORM_ENV}" -- python scripts/build_wheels.py \
    --platform-env "${PLATFORM_ENV}" \
    --itk-git-tag "${ITK_REF}" \
    --itk-source-dir "${WORKDIR}/ITK" \
    --module-source-dir "${MODULES_DIR}/${name}" \
    --no-build-itk-tarball-cache \
    --no-use-sudo \
    --skip-itk-build \
    --skip-itk-wheel-build \
    --build-dir-root "${WORKDIR}/build" 2>&1; then
    cp "${MODULES_DIR}/${name}"/dist/*.whl "${DIST_DIR}/" 2>/dev/null || true
  else
    echo "  FAILED: ${name}"
    failed_modules+=("${name}")
  fi
done

# 6) Summary
echo ""
echo "=== Build complete ==="
echo "Wheels: ${DIST_DIR}"
find "${DIST_DIR}" -maxdepth 1 -name '*.whl' | wc -l
echo "total wheels produced"

if [ ${#failed_modules[@]} -gt 0 ]; then
  echo ""
  echo "Failed modules (${#failed_modules[@]}):"
  printf '  %s\n' "${failed_modules[@]}"
fi
