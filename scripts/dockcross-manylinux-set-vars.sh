#!/bin/bash

# Run this script to set enviroment variables used in building the 
# ITK Python wheel packages for Linux.
#
# ENVIRONMENT VARIABLES
# These environment variables will be populated by the script when invoked with `source`
# if their value is not set with `export` before invocation.
# For example,
#
#   export ITK_PACKAGE_VERSION=v5.3.0
#   scripts/dockcross-manylinux-set-vars.sh cp39
#

########################################################################
# ITKPythonBuilds parameters

# ITKPythonBuilds archive tag to use for ITK build artifacts.
#   See https://github.com/insightSoftwareConsortium/ITKpythonbuilds for available tags.
ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION:=v5.3.0}

# Github organization for fetching ITKPythonPackage build scripts
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}

# ITKPythonPackage tag for fetching build scripts
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG:=master}

########################################################################
# Docker image parameters

# Specialized manylinux image to use for building. Default is _2_28.
#   See https://github.com/dockcross/dockcross for available versions and tags.
MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28}

# Specialized manylinux image tag to use for building.
if [[ ${MANYLINUX_VERSION} == _2_28 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=20221205-459c9f0}
elif [[ ${MANYLINUX_VERSION} == 2014 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=20221201-fd49c08}
else
  echo "Unknown manylinux version ${MANYLINUX_VERSION}"
  exit 1;
fi
