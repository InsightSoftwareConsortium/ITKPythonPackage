#!/bin/bash

########################################################################
# Run this script to set common enviroment variables used in building the
# ITK Python wheel packages for Linux.
#
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

# - `ITK_PACKAGE_VERSION`: Tag/branch/hash for ITKPythonBuilds build cache to use
#     Examples: "v5.4.0", "v5.2.1.post1" "0ffcaed12552" "my-testing-branch"
#     See available tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags
ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION:=v6.0b01}

# - `ITKPYTHONPACKAGE_ORG`: Github organization or user to use for ITKPythonPackage build scripts
#     build script source. Default is InsightSoftwareConsortium.
#     Ignored if ITKPYTHONPACKAGE_TAG is empty.
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}

# - `ITKPYTHONPACKAGE_TAG`: Tag for ITKPythonPackage build scripts to use.
#     If ITKPYTHONPACKAGE_TAG is empty then the default scripts distributed
#     with the ITKPythonBuilds archive will be used.
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG:=main}

########################################################################
# Docker image parameters

# - `MANYLINUX_VERSION`: Specialized manylinux image to use for building. Default is _2_28.
#     Examples: "_2_28", "2014"
#   See https://github.com/dockcross/dockcross for available versions and tags.
#   For instance, `export MANYLINUX_VERSION=_2_34`
MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28} # <- The primary support target for ITK as of 20251114.  Including upto Python 3.15 builds.

# - `TARGET_ARCH`: Target architecture for which wheels should be built.
# Target platform architecture (x64, aarch64)
TARGET_ARCH=${TARGET_ARCH:=x64}

# - `IMAGE_TAG`: Specialized manylinux image tag to use for building.
#   For instance, `export IMAGE_TAG=20221205-459c9f0`.
#   Tagged images are available at:
#   - https://github.com/dockcross/dockcross (x64 architecture)
#   - https://quay.io/organization/pypa (ARM architecture)
if [[ ${MANYLINUX_VERSION} == _2_34 && ${TARGET_ARCH} == x64 ]]; then
  # https://hub.docker.com/r/dockcross/manylinux_2_34-x64/tags
  IMAGE_TAG=${IMAGE_TAG:=latest}  #<- as of 20251114 this should primarily be used for testing
elif [[ ${MANYLINUX_VERSION} == _2_28 && ${TARGET_ARCH} == x64 ]]; then
  # https://hub.docker.com/r/dockcross/manylinux_2_28-x64/tags
  IMAGE_TAG=${IMAGE_TAG:=20251011-8b9ace4}
elif [[ ${MANYLINUX_VERSION} == _2_28 && ${TARGET_ARCH} == aarch64 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=2025.08.12-1}
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

# - `LD_LIBRARY_PATH`: Shared libraries to be included in the resulting wheel.
#   For instance, `export LD_LIBRARY_PATH="/path/to/OpenCL.so:/path/to/OpenCL.so.1.2"`
LD_LIBRARY_PATH=${LD_LIBRARY_PATH:=}

# - `NO_SUDO`:
# Disable if running docker does not require sudo priveleges
# (set to 1 if your user account can run docker).
NO_SUDO=${NO_SUDO:=}
#
# - `ITK_MODULE_NO_CLEANUP`: Option to skip cleanup steps.
#    =1 <- Leave tempoary build files in place after completion
ITK_MODULE_NO_CLEANUP=${ITK_MODULE_NO_CLEANUP:=}

# - `ITK_MODULE_PREQ`: Prerequisite ITK modules that must be built before the requested module.
#   Format is `<org_name>/<module_name>@<module_tag>:<org_name>/<module_name>@<module_tag>:...`.
#   For instance, `export ITK_MODULE_PREQ=InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0`
#   See notes in `dockcross-manylinux-build-module-deps.sh`.
ITK_MODULE_PREQ=${ITK_MODULE_PREQ:=}

script_dir=${script_dir:=$(cd $(dirname $0) || exit 1; pwd)}
source "${script_dir}/oci_exe.sh"
oci_exe=${oci_exe:=$(ociExe)}

_local_script_name=${script_name:-UNKNOWN_LOCATION}

# - `DOCKCROSS_ENV_REPORT`: A path to document the environment variables used in this build
DOCKCROSS_ENV_REPORT=${DOCKCROSS_ENV_REPORT:=$(mktemp /tmp/dockcross_${_local_script_name}.XXXXXX)}
cat > ${DOCKCROSS_ENV_REPORT} << OVERRIDE_ENV_SETTINGS
################################################
################################################
###  ITKPythonPackage Environment Variables  ###
###    (sourced from ${_local_script_name} ) ###

# Which ITK git tag/hash/branch to use as reference for building wheels/modules
# https://github.com/InsightSoftwareConsortium/ITK.git@\${ITK_PACKAGE_VERSION}
export ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION}

# Which script version to use in generating python packages
# https://github.com/InsightSoftwareConsortium/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git@\${ITKPYTHONPACKAGE_TAG}
export ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG}
export ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG}

# Which container to use for generating cross compiled packages
export oci_exe=${oci_exe}   # The container run environment
export MANYLINUX_VERSION=${MANYLINUX_VERSION}
export TARGET_ARCH=${TARGET_ARCH}
export IMAGE_TAG=${IMAGE_TAG}
# Almost never change MANYLINUX_IMAGE_NAME or CONTAINER_SOURCE directly
# export MANYLINUX_IMAGE_NAME="manylinux\${MANYLINUX_VERSION}-\${TARGET_ARCH}:\${IMAGE_TAG}"
# export CONTAINER_SOURCE=${CONTAINER_SOURCE}

# Environmental controls impacting dockcross-manylinux-build-module-wheels.sh
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}
export NO_SUDO=${NO_SUDO}
export ITK_MODULE_NO_CLEANUP=${ITK_MODULE_NO_CLEANUP}
export ITK_MODULE_PREQ=${ITK_MODULE_PREQ}

################################################
################################################
OVERRIDE_ENV_SETTINGS
cat ${DOCKCROSS_ENV_REPORT}
