#!/usr/bin/env bash
set -euo pipefail

echo "=== macOS Build Environment Sanity Check ==="
echo

# Simple helper
have() { command -v "$1" >/dev/null 2>&1; }

# -----------------------------
# 1. Basic OS / Xcode / CLT info
# -----------------------------
echo "[1] System / Xcode / Toolchain"

sw_vers || echo "sw_vers: not available"

if have xcodebuild; then
  echo "Xcode path:      $(xcodebuild -print-path 2>/dev/null || echo 'N/A')"
  echo "Xcode version:   $(xcodebuild -version 2>/dev/null | tr '\n' ' ' || echo 'N/A')"
else
  echo "Xcode:           NOT FOUND (xcodebuild missing)"
fi

if have clang; then
  echo "Clang version:   $(clang --version | head -n1)"
else
  echo "Clang:           NOT FOUND"
fi
echo

# -----------------------------
# 2. SDKROOT / SDK version
# -----------------------------
echo "[2] SDKROOT / SDK selection"

if have xcrun; then
  XCRUN_SDK_PATH="$(xcrun --sdk macosx --show-sdk-path 2>/dev/null || true)"
  XCRUN_SDK_VER="$(xcrun --sdk macosx --show-sdk-version 2>/dev/null || true)"
else
  XCRUN_SDK_PATH=""
  XCRUN_SDK_VER=""
fi

echo "xcrun SDK path:  ${XCRUN_SDK_PATH:-'(none)'}"
echo "xcrun SDK ver:   ${XCRUN_SDK_VER:-'(none)'}"

SDKROOT_ENV="${SDKROOT:-}"
if [[ -n "${SDKROOT_ENV}" ]]; then
  echo "SDKROOT (env):   ${SDKROOT_ENV}"
  if [[ ! -d "${SDKROOT_ENV}" ]]; then
    echo "  [ERROR] SDKROOT points to a non-existent directory."
  elif [[ -n "${XCRUN_SDK_PATH}" && "${SDKROOT_ENV}" != "${XCRUN_SDK_PATH}" ]]; then
    echo "  [WARN] SDKROOT differs from xcrun SDK path."
  fi
else
  echo "SDKROOT (env):   (not set)"
fi
echo

# -----------------------------
# 3. Deployment target
# -----------------------------
echo "[3] Deployment target"

MAC_DEPLOY="${MACOSX_DEPLOYMENT_TARGET:-}"
if [[ -n "${MAC_DEPLOY}" ]]; then
  echo "MACOSX_DEPLOYMENT_TARGET: ${MAC_DEPLOY}"

  # Normalize to major.minor (strip patch if present)
  DEPLOY_NORM="${MAC_DEPLOY%%.*}.${MAC_DEPLOY#*.}"
  DEPLOY_NORM="${DEPLOY_NORM%%.*}.${DEPLOY_NORM#*.}"  # crude trim to 2 components

  if [[ ! "${DEPLOY_NORM}" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "  [ERROR] MACOSX_DEPLOYMENT_TARGET is not a valid numeric version."
  fi

  if [[ -n "${XCRUN_SDK_VER}" ]]; then
    # Compare major.minor numerically
    sdk_major="${XCRUN_SDK_VER%%.*}"
    sdk_minor="${XCRUN_SDK_VER#*.}"; sdk_minor="${sdk_minor%%.*}"
    dep_major="${DEPLOY_NORM%%.*}"
    dep_minor="${DEPLOY_NORM#*.}"; dep_minor="${dep_minor%%.*}"

    if (( dep_major > sdk_major || (dep_major == sdk_major && dep_minor > sdk_minor) )); then
      echo "  [ERROR] Deployment target (${DEPLOY_NORM}) is NEWER than SDK version (${XCRUN_SDK_VER})."
      echo "         This can cause compile/link failures."
    fi
  fi
else
  echo "MACOSX_DEPLOYMENT_TARGET: (not set)"
fi
echo

# -----------------------------
# 4. CMake-related variables
# -----------------------------
echo "[4] CMake-related macOS variables"

CMAKE_SYSROOT="${CMAKE_OSX_SYSROOT:-}"
if [[ -n "${CMAKE_SYSROOT}" ]]; then
  echo "CMAKE_OSX_SYSROOT (env):  ${CMAKE_SYSROOT}"
  if [[ ! -d "${CMAKE_SYSROOT}" ]]; then
    echo "  [ERROR] CMAKE_OSX_SYSROOT directory does not exist."
  elif [[ -n "${XCRUN_SDK_PATH}" && "${CMAKE_SYSROOT}" != "${XCRUN_SDK_PATH}" ]]; then
    echo "  [WARN] CMAKE_OSX_SYSROOT differs from xcrun SDK path."
  fi
else
  echo "CMAKE_OSX_SYSROOT (env):  (not set)"
fi

CMAKE_DEPLOY="${CMAKE_OSX_DEPLOYMENT_TARGET:-}"
if [[ -n "${CMAKE_DEPLOY}" ]]; then
  echo "CMAKE_OSX_DEPLOYMENT_TARGET (env): ${CMAKE_DEPLOY}"
else
  echo "CMAKE_OSX_DEPLOYMENT_TARGET (env): (not set)"
fi

CMAKE_ARCHS="${CMAKE_OSX_ARCHITECTURES:-}"
if [[ -n "${CMAKE_ARCHS}" ]]; then
  echo "CMAKE_OSX_ARCHITECTURES (env):     ${CMAKE_ARCHS}"
else
  echo "CMAKE_OSX_ARCHITECTURES (env):     (not set)"
fi
echo

# -----------------------------
# 5. ARCHFLAGS / Python builds
# -----------------------------
echo "[5] ARCHFLAGS (Python / generic builds)"

ARCHFLAGS_ENV="${ARCHFLAGS:-}"
if [[ -n "${ARCHFLAGS_ENV}" ]]; then
  echo "ARCHFLAGS:        ${ARCHFLAGS_ENV}"
else
  echo "ARCHFLAGS:        (not set)"
fi
echo

echo "=== Summary ==="
if [[ -n "${MAC_DEPLOY}" && -n "${XCRUN_SDK_VER}" ]]; then
  echo "Using SDK ${XCRUN_SDK_VER} with deployment target ${MAC_DEPLOY}."
elif [[ -n "${XCRUN_SDK_VER}" ]]; then
  echo "Using SDK ${XCRUN_SDK_VER} with no explicit deployment target."
else
  echo "SDK version could not be determined via xcrun."
fi

echo "Check above for [ERROR] and [WARN] markers."
