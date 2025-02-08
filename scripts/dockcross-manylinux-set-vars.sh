#!/bin/bash

########################################################################
# Run this script to set common enviroment variables used in building the 
# ITK Python wheel packages for Linux.
#
# ENVIRONMENT VARIABLES
# These environment variables will be populated by the script when invoked with `source`
# if their value is not set with `export` before invocation.
# For example,
#
#   export ITK_PACKAGE_VERSION=v5.4.0
#   scripts/dockcross-manylinux-set-vars.sh cp39
#
########################################################################

########################################################################
# ITKPythonBuilds parameters

# ITKPythonBuilds archive tag to use for ITK build artifacts.
#   See https://github.com/insightSoftwareConsortium/ITKpythonbuilds for available tags.
ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION:=v5.4.0}

# Github organization for fetching ITKPythonPackage build scripts
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}

# ITKPythonPackage tag for fetching build scripts
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG:=master}

########################################################################
# Docker image parameters

# Specialized manylinux image to use for building. Default is _2_28.
#   See https://github.com/dockcross/dockcross for available versions and tags.
MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28}

# Target platform architecture (x64, aarch64)
TARGET_ARCH=${TARGET_ARCH:=x64}

if  ${TARGET_ARCH} == x86_64 || ${TARGET_ARCH} == amd64 ]; then
   echo "WARNING:  x86_64 and amd64 are equivalent to x64,"
   echo "          use x64 as TARGET_ARCH."
   exit 255
fi

# Specialized manylinux image tag to use for building.
if [[ ${MANYLINUX_VERSION} == _2_28 && ${TARGET_ARCH} == x64 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=20240304-9e57d2b}
elif [[ ${MANYLINUX_VERSION} == _2_28 && ${TARGET_ARCH} == aarch64 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=2024-03-25-9206bd9}
elif [[ ${MANYLINUX_VERSION} == 2014 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=20240304-9e57d2b}
else
  echo "Unknown manylinux version ${MANYLINUX_VERSION}"
  exit 1;
fi

# Set container for requested version/arch/tag.
if [[ ${TARGET_ARCH} == x64 ]]; then
  MANYLINUX_IMAGE_NAME=${MANYLINUX_IMAGE_NAME:="manylinux${MANYLINUX_VERSION}-${TARGET_ARCH}:${IMAGE_TAG}"}
  CONTAINER_SOURCE="docker.io/dockcross/${MANYLINUX_IMAGE_NAME}"
elif [[ ${TARGET_ARCH} == aarch64 ]]; then
  MANYLINUX_IMAGE_NAME=${MANYLINUX_IMAGE_NAME:="manylinux${MANYLINUX_VERSION}_${TARGET_ARCH}:${IMAGE_TAG}"}
  CONTAINER_SOURCE="quay.io/pypa/${MANYLINUX_IMAGE_NAME}"
else
  echo "Unknown target architecture ${TARGET_ARCH}"
  exit 1;
fi
