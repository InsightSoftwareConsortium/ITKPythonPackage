#!/bin/bash

########################################################################
# Run this script to set common enviroment variables used in building the
# ITK Python wheel packages for Linux.
#
# These environment variables will be populated by the script
# when invoked with `source ${_ipp_dir}/build/package.env`
# if their value is not set with `export` before invocation.
# For example,
#
#   export ITK_GIT_TAG=main
#
########################################################################

_ipp_dir=$(cd $(dirname $0) || exit 1; pwd)
_DOCKCROSS_ENV_REPORT=${_ipp_dir}/build/package.env
if [ -f "${_DOCKCROSS_ENV_REPORT}" ]; then
  # If file exists, generate candidate file instead
  _candidate_config_filename=${_DOCKCROSS_ENV_REPORT}_$(date +"%y%m%d")
  echo "${_DOCKCROSS_ENV_REPORT} exists, generating candidate ${_candidate_config_filename} instead"

  # pre-load existing values
  source "${_DOCKCROSS_ENV_REPORT}"
  _DOCKCROSS_ENV_REPORT=${_candidate_config_filename}
fi

# Assume that ITKPythonPackage tags are identical to ITK tags
_ipp_latest_tag=$(git tag --sort=v:refname | tail -1)
if [ "${ITK_GIT_TAG}" != "${_ipp_latest_tag}" ] ;then
  _IPP_ITK_SOURCE_DIR=${_ipp_dir}/ITK-source/ITK
  # Need early checkout to get AUTOVERSION
  if [ ! -d "${_IPP_ITK_SOURCE_DIR}" ]; then
    git clone https://github.com/InsightSoftwareConsortium/ITK.git ${_IPP_ITK_SOURCE_DIR}
  fi
  pushd "${_IPP_ITK_SOURCE_DIR}" > /dev/null 2>&1
    git fetch --tags
    git checkout ${ITK_GIT_TAG}
    # Get auto generated itk package version
    _ipp_latest_version=$( git describe --tags --long --dirty --always \
         | sed -E 's/^([^-]+)-([0-9]+)-g([0-9a-f]+)(-dirty)?$/\1-dev.\2+\3\4/'
      )
  popd > /dev/null 2>&1
fi


########################################################################
# ITKPythonBuilds parameters
ITK_GIT_TAG=${ITK_GIT_TAG:=${_ipp_latest_tag}}
ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION:=${_ipp_latest_version}}
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG:=${_ipp_latest_tag}}

########################################################################
# Docker image parameters
MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28} # <- The primary support target for ITK as of 20251114.  Including upto Python 3.15 builds.
TARGET_ARCH=${TARGET_ARCH:=x64}

if [[ ${MANYLINUX_VERSION} == _2_34 && ${TARGET_ARCH} == x64 ]]; then
  # https://hub.docker.com/r/dockcross/manylinux_2_34-x64/tags
  IMAGE_TAG=${IMAGE_TAG:=latest}  #<- as of 20251114 this should primarily be used for testing
elif [[ ${MANYLINUX_VERSION} == _2_28 && ${TARGET_ARCH} == x64 ]]; then
  # https://hub.docker.com/r/dockcross/manylinux_2_28-x64/tags
  # IMAGE_TAG=${IMAGE_TAG:=20251011-8b9ace4} # <- Incompatible with ITK cast-xml on 2025-11-16
  IMAGE_TAG=${IMAGE_TAG:=20250913-6ea98ba}
elif [[ ${MANYLINUX_VERSION} == _2_28 && ${TARGET_ARCH} == aarch64 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=2025.08.12-1}
elif [[ ${MANYLINUX_VERSION} == 2014 ]]; then
  IMAGE_TAG=${IMAGE_TAG:=20240304-9e57d2b}
else
  echo "Unknown manylinux version ${MANYLINUX_VERSION}"
  exit 1;
fi

LD_LIBRARY_PATH=${LD_LIBRARY_PATH:=}
NO_SUDO=${NO_SUDO:=}
ITK_MODULE_NO_CLEANUP=${ITK_MODULE_NO_CLEANUP:=}
ITK_MODULE_PREQ=${ITK_MODULE_PREQ:=}
source "${_ipp_dir}/scripts/oci_exe.sh"
oci_exe=${oci_exe:=$(ociExe)}

# Setup system dependant compiler options
if [[ "$(uname)" == "Darwin" ]]; then
  cmake --system-information > build/cmake_system_information 2>&1
fi

cat > ${_DOCKCROSS_ENV_REPORT} << DEFAULT_ENV_SETTINGS
################################################
################################################
###  ITKPythonPackage Environment Variables  ###
###  in .env format (KEY=VALUE)              ###

# - "ITK_GIT_TAG": Tag/branch/hash for ITKPythonBuilds build cache to use
#   Which ITK git tag/hash/branch to use as reference for building wheels/modules
#   https://github.com/InsightSoftwareConsortium/ITK.git@\${ITK_GIT_TAG}
#   Examples: "v5.4.0", "v5.2.1.post1" "0ffcaed12552" "my-testing-branch"
#   See available tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags
ITK_GIT_TAG=${ITK_GIT_TAG}

# - "ITK_SOURCE_DIR":  When building different "flavor" of ITK python packages
# on a given platform, explicitly setting the ITK_SOURCE_DIR options allow to
# speed up source-code downloads by re-using an existing repository.
ITK_SOURCE_DIR=${_ipp_dir}/ITK-source/ITK

#
# - : "ITK_PACKAGE_VERSION" A valid versioning formatted tag.  This may be ITK_GIT_TAG for tagged releaseds
#     Use the keyword 'AUTOVERSION' to have a temporary version automatically created from based on
#     git hash and the checked out ITK_GIT_TAG
ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION}

# - "ITKPYTHONPACKAGE_ORG": Github organization or user to use for ITKPythonPackage build scripts
#   Which script version to use in generating python packages
#   https://github.com/InsightSoftwareConsortium/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git@\${ITKPYTHONPACKAGE_TAG}
#   build script source. Default is InsightSoftwareConsortium.
#   Ignored if ITKPYTHONPACKAGE_TAG is empty.
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG}

# - "ITKPYTHONPACKAGE_TAG": Tag for ITKPythonPackage build scripts to use.
#   If ITKPYTHONPACKAGE_TAG is empty then the default scripts distributed
#   with the ITKPythonBuilds archive will be used.
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG}

# Which container to use for generating cross compiled packages
oci_exe=${oci_exe}   # The container run environment

# - "MANYLINUX_VERSION": Specialized manylinux image to use for building. Default is _2_28.
#   Examples: "_2_28", "2014"
#   See https://github.com/dockcross/dockcross for available versions and tags.
#   For instance, "export MANYLINUX_VERSION=_2_34"
MANYLINUX_VERSION=${MANYLINUX_VERSION}

# - "TARGET_ARCH": Target architecture for which wheels should be built.
#   Target platform architecture (x64, aarch64)
TARGET_ARCH=${TARGET_ARCH}

# - "IMAGE_TAG": Specialized manylinux image tag to use for building.
#   For instance, "export IMAGE_TAG=20221205-459c9f0".
#   Tagged images are available at:
#   - https://github.com/dockcross/dockcross (x64 architecture)
#   - https://quay.io/organization/pypa (ARM architecture)
IMAGE_TAG=${IMAGE_TAG}

# Environmental controls impacting dockcross-manylinux-build-module-wheels.sh
# - "LD_LIBRARY_PATH": Shared libraries to be included in the resulting wheel.
#   For instance, "export LD_LIBRARY_PATH="/path/to/OpenCL.so:/path/to/OpenCL.so.1.2""
LD_LIBRARY_PATH=${LD_LIBRARY_PATH}

# - "NO_SUDO":
#   Disable if running docker does not require sudo priveleges
#   (set to 1 if your user account can run docker).
NO_SUDO=${NO_SUDO}

# - "ITK_MODULE_NO_CLEANUP": Option to skip cleanup steps.
#   =1 <- Leave tempoary build files in place after completion
ITK_MODULE_NO_CLEANUP=${ITK_MODULE_NO_CLEANUP}

# - "ITK_MODULE_PREQ": Prerequisite ITK modules that must be built before the requested module.
#   Format is "<org_name>/<module_name>@<module_tag>:<org_name>/<module_name>@<module_tag>:...".
#   For instance, "export ITK_MODULE_PREQ=InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0"
#   See notes in "dockcross-manylinux-build-module-deps.sh".
ITK_MODULE_PREQ=${ITK_MODULE_PREQ}

# "[DYLD|LD]_LIBRARY_PATH": Shared libraries to be included in the resulting wheel.
#   For instance, export [DYLD|LD]_LIBRARY_PATH="/path/to/OpenCL.so:/path/to/OpenCL.so.1.2"
DYLD_LIBRARY_PATH=${DYLD_LIBRARY_PATH}
LD_LIBRARY_PATH=${LD_LIBRARY_PATH}
#
# "ITK_USE_LOCAL_PYTHON": For APPLE ONLY Determine how to get Python framework for build.
#    - If empty, Python frameworks will be fetched from python.org
#    - If not empty, frameworks already on machine will be used without fetching.
ITK_USE_LOCAL_PYTHON=${ITK_USE_LOCAL_PYTHON}

# CC=$( cat build/cmake_system_information| grep "CMAKE_C_COMPILER == " | tr " " "\n" |sed -n "3p")
# CXX=$(cat build/cmake_system_information| grep "CMAKE_CXX_COMPILER == " | tr " " "\n" |sed -n "3p")

################################################
DEFAULT_ENV_SETTINGS
cat ${_DOCKCROSS_ENV_REPORT}
