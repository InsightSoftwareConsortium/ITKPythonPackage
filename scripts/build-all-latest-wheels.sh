#!/bin/bash
# Build ITK + all remote module Python wheels from latest main branches.
# Usage: ./scripts/build-all-latest-wheels.sh [platform-env]
# Example: ./scripts/build-all-latest-wheels.sh linux-py311
set -euo pipefail

PLATFORM_ENV="${1:-linux-py311}"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
WORKDIR="/tmp/${TIMESTAMP}_LatestITKPython"
DIST_DIR="${WORKDIR}/dist"
ITK_REPO="https://github.com/InsightSoftwareConsortium/ITK.git"
IPP_REPO="https://github.com/BRAINSia/ITKPythonPackage.git"
IPP_BRANCH="python-build-system"

mkdir -p "${DIST_DIR}"
echo "=== Build directory: ${WORKDIR}"
echo "=== Platform: ${PLATFORM_ENV}"

# 1) Clone ITK
echo "=== Cloning ITK (main)..."
git clone --depth 1 --branch main "${ITK_REPO}" "${WORKDIR}/ITK"

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
      rm -rf "${MODULES_DIR}/${name}"
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
    --itk-git-tag main \
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
ls -1 "${DIST_DIR}"/*.whl 2>/dev/null | wc -l
echo "total wheels produced"

if [ ${#failed_modules[@]} -gt 0 ]; then
  echo ""
  echo "Failed modules (${#failed_modules[@]}):"
  printf '  %s\n' "${failed_modules[@]}"
fi
