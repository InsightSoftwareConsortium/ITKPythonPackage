#!/bin/bash

########################################################################
# Run this script to set common enviroment variables used in building the
# ITK Python wheel packages for Linux.
#
# Any environmental variables that are exported in the calling environment,
# or # previously set in the input (-i) file will be retained.
#
# NOTE: only variables that are "exported" will be retained. To override
#       values, use a set of VAR1=VALUE1  VAR2=VALUE2 elements at then
#       end of the command line
#
# These environment variables will be populated by the script
# when invoked with `source ${_ipp_dir}/build/package.env`
# if their value is not set with `export` before invocation.
# For example,
#
#   export ITK_GIT_TAG=main
#   export ITK_SOURCE_DIR=/home/me/src/ITK
#   NO_SUDO=1 <-- WARNING This will only be set in calling environment
#                         and not seen during generation of new -o <file>.env
#
########################################################################

usage() {
    echo "Usage:"
    echo "export KEY0=VALUE0"
    echo "$0 [-i input_file] [-o output_file] [KEY1=VALUE1  KEY2=VALUE2 ...]"
    echo "PRIORITY OF SETTING VALUES"
    echo "   lowest 0: guessed values not declared elsewhere"
    echo "          1: exported environmental variables. i.e. KEY0"
    echo "          2: mappings specified in input_file mappings"
    echo "  highest 3: mappings given at the end of the command line. i.e. KEY1, KEY2"
    exit 1
}

# Detect whether the script is being sourced
sourced=0
# ZSH
if [ -n "${ZSH_VERSION:-}" ]; then
    case $ZSH_EVAL_CONTEXT in
        *:file) sourced=1 ;;
    esac
# BASH
elif [ -n "${BASH_VERSION:-}" ]; then
    # test whether $0 is the current shell, or $BASH_SOURCE differs
    [[ "${BASH_SOURCE[0]}" != "$0" ]] && sourced=1
# POSIX fallback: last resort
else
    # If 'return' works, we're sourced. If it errors, we're executed.
    (return 0 2>/dev/null) && sourced=1
fi

if [ "$sourced" -eq 1 ]; then
    echo "*************************************************************"
    echo "* Never source $0 script directly!"
    echo "*"
    echo "* Run as a script (i.e. 'ITK_SOURCE_DIR=/home/me/src/ITK bash $0')"
    echo "*    then 'source build/package.env' that results from the run"
    echo "*************************************************************"
    return
fi

_ipp_dir=$(cd $(dirname $0) || exit 1; pwd)
BUILD_ENV_REPORT=${BUILD_ENV_REPORT:=${_ipp_dir}/build/package.env}
if [ -f "${BUILD_ENV_REPORT}" ]; then
  REFERENCE_ENV_REPORT="${BUILD_ENV_REPORT}"
else
  REFERENCE_ENV_REPORT=""
fi

# Reset OPTIND so sourcing/re-running doesn't break parsing
OPTIND=1
while getopts ":i:o:h" opt; do
    case "$opt" in
        i)
            REFERENCE_ENV_REPORT="$OPTARG"
            ;;
        o)
            BUILD_ENV_REPORT="$OPTARG"
            ;;
        h)
            usage
            ;;
        :)
            echo "ERROR: Option -$OPTARG requires an argument" >&2
            usage
            ;;
        \?)
            echo "ERROR: Unknown option -$OPTARG" >&2
            usage
            ;;
    esac
done
shift $((OPTIND - 1))     # remove parsed flags from "$@"

echo "Input:   ${REFERENCE_ENV_REPORT:-<none>}"
echo "Output:  ${BUILD_ENV_REPORT:-<none>}"

if [ -f "${REFERENCE_ENV_REPORT}" ]; then
  if [ "${REFERENCE_ENV_REPORT}" = "${BUILD_ENV_REPORT}" ]; then
    # If BUILD_ENV_REPORT exists, make a backup
    _candidate_config_filename=${BUILD_ENV_REPORT}_$(date +"%y%m%d.%H%M%S")
    echo "${BUILD_ENV_REPORT} exists, backing up to ${_candidate_config_filename}"
    cp ${BUILD_ENV_REPORT} ${_candidate_config_filename}
  fi
  # pre-load existing values
  source "${REFERENCE_ENV_REPORT}"
fi

# ---- Process trailing KEY=VALUE pairs that are intended to override previously stored values ----
for kv in "$@"; do
    case "$kv" in
        *=*)
            key=${kv%%=*}
            value=${kv#*=}
            if [[ "${value}" = "UNSET" ]]; then
               unset ${key}
               continue
            fi
            # Enforce valid shell identifier for the key
            case "$key" in
                ''|*[!A-Za-z0-9_]*)
                    echo "ERROR: Invalid variable name '$key' in '$kv'" >&2
                    exit 1
                    ;;
                [0-9]*)
                    echo "ERROR: Invalid variable name '$key' (cannot start with digit)" >&2
                    exit 1
                    ;;
            esac

            # Export into environment for downstream tools
            export "$key=$value"
            ;;
        *)
            echo "ERROR: Trailing argument '$kv' is not KEY=VALUE" >&2
            usage
            ;;
    esac
done


# Must run inside a git working tree
get_git_id() {
  # 1. If current commit has an exact tag (no -gXXXX suffix)
  if tag=$(git describe --tags --exact-match 2>/dev/null); then
      echo "$tag"
      return
  fi

  # 2. If on a branch
  if branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) && [[ "$branch" != "HEAD" ]]; then
      echo "$branch"
      return
  fi

  # 3. Detached HEAD → fallback to short hash
  git rev-parse --short HEAD
}

# portable_indirect VAR_NAME → prints value of
# the variable that VAR_NAME points to in both zsh
# and bash
indirect() {
    local ref="$1"
    if [ -n "${ZSH_VERSION:-}" ]; then
        # zsh: use (P) flag
        print -r -- ${(P)ref}
    else
        # bash: use ${!name}
        printf '%s\n' "${!ref}"
    fi
}

# -----------------------------------------------------------------------
# -----------------------------------------------------------------------
# Install setup platform dependant executables
# Ensure that required executables are found for each platform
case "$(uname -s)" in
    Linux*)
        OS=linux
        # Install prerequirements
        export PATH=${_ipp_dir}/tools/doxygen-1.8.16/bin:$PATH
        case $(uname -m) in
            i686)
                ;;
            x86_64)
                if ! type doxygen > /dev/null 2>&1; then
                  mkdir -p ${_ipp_dir}/tools
                    pushd ${_ipp_dir}/tools > /dev/null 2>&1
                    curl https://data.kitware.com/api/v1/file/62c4d615bddec9d0c46cb705/download -o doxygen-1.8.16.linux.bin.tar.gz
                    tar -xvzf doxygen-1.8.16.linux.bin.tar.gz
                  popd > /dev/null 2>&1
                  DOXYGEN_EXECUTABLE=${_ipp_dir}/tools/doxygen-1.8.16/bin/doxygen
                fi
                ;;
            aarch64)
                if ! type doxygen > /dev/null 2>&1; then
                  mkdir -p ${_ipp_dir}/tools
                  pushd ${_ipp_dir}/tools > /dev/null 2>&1
                    curl https://data.kitware.com/api/v1/file/62c4ed58bddec9d0c46f1388/download -o doxygen-1.8.16.linux.aarch64.bin.tar.gz
                    tar -xvzf doxygen-1.8.16.linux.aarch64.bin.tar.gz
                  popd > /dev/null 2>&1
                  DOXYGEN_EXECUTABLE=${_ipp_dir}/tools/doxygen-1.8.16/bin/doxygen
                fi
                ;;
            *)
                die "Unknown architecture $(uname -m)"
                ;;
        esac
        if ! type ninja > /dev/null 2>&1; then
          if test ! -d ninja; then
            git clone https://github.com/ninja-build/ninja.git
          fi
          pushd ninja
          git checkout release
          cmake -Bbuild-cmake -H.
          cmake --build build-cmake
          sudo cp build-cmake/ninja /usr/local/bin/
          popd
          NINJA_EXECUTABLE=/usr/local/bin/ninja
        fi
        ;;
    Darwin*)
        OS=darwin
        brew info doxygen | grep --quiet 'Not installed' && brew update && brew install doxygen
        brew info ninja | grep --quiet 'Not installed' && brew update && brew install ninja
        brew info cmake | grep --quiet 'Not installed' && brew update && brew install cmake
        ;;

    CYGWIN*|MINGW*|MSYS*)
        OS=windows
        echo "WINDOWS NOT SUPPORTED WITH BASH ENVIRONMENTAL VARIABLES"
        exit 1
        ;;

    *)
        echo "Unsupported platform: $(uname -s)" >&2
        exit 1
        ;;
esac
DOXYGEN_EXECUTABLE=${DOXYGEN_EXECUTABLE:=$(which doxygen)}
NINJA_EXECUTABLE=${NINJA_EXECUTABLE:=$(which ninja)}
CMAKE_EXECUTABLE=${CMAKE_EXECUTABLE:=$(which cmake)}
for required_exec in DOXYGEN_EXECUTABLE NINJA_EXECUTABLE CMAKE_EXECUTABLE; do
  if [ ! -f "$(indirect $required_exec)" ]; then
     echo "MISSING: ${required_exec} not found at $(indirect $required_exec)"
     echo "aborting until required executables can be found"
     exit 1
  fi
done
# -----------------------------------------------------------------------

ITK_SOURCE_DIR=${ITK_SOURCE_DIR:=${_ipp_dir}/ITK-source/ITK}

# determine the latest tag for ITKPythonPackage (current working directory)
pushd "${_ipp_dir}" || echo "can not enter ${ipp_dir}"
  _ipp_latest_tag="$(get_git_id)"
popd
if [ ! -d "${ITK_SOURCE_DIR}" ]; then
  # Need early checkout to get AUTOVERSION if none provided
  git clone https://github.com/InsightSoftwareConsortium/ITK.git ${ITK_SOURCE_DIR}
fi
pushd "${ITK_SOURCE_DIR}" || echo "cannot enter ${ITK_SOURCE_DIR}"
  git checkout ${ITK_GIT_TAG}
popd
# If the ITK_GIT_TAG != the ITKPythonPackage latest tag,
# then get a value to auto-generate the python packaging name
if [ -z "${ITK_PACKAGE_VERSION}" ]; then
  if [ "${ITK_GIT_TAG}" = "${_ipp_latest_tag}" ]; then
    ITK_PACKAGE_VERSION=${ITK_GIT_TAG}
  else
    # Get auto generated itk package version base semantic versioning
    # rules for relative versioning based on git commits
    pushd "${ITK_SOURCE_DIR}" || echo "cannot enter ${ITK_SOURCE_DIR}"
      git fetch --tags
      git checkout ${ITK_GIT_TAG}
      ITK_PACKAGE_VERSION=$( git describe --tags --long --dirty --always \
             | sed -E 's/^([^-]+)-([0-9]+)-g([0-9a-f]+)(-dirty)?$/\1-dev.\2+\3\4/'
          )
    popd
  fi
fi

########################################################################
# Docker image parameters
MANYLINUX_VERSION=${MANYLINUX_VERSION:=_2_28} # <- The primary support target for ITK as of 20251114.  Including upto Python 3.15 builds.
case $(uname -m) in
    i686)
        TARGET_ARCH=x86
        ;;
    x86_64)
        TARGET_ARCH=x64
        ;;
    aarch64)
        TARGET_ARCH=aarch64
        ;;
    *)
        die "Unknown architecture $(uname -m)"
        ;;
esac

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
#
# Set container for requested version/arch/tag.
if [[ ${TARGET_ARCH} == x64 ]]; then
  MANYLINUX_IMAGE_NAME=${MANYLINUX_IMAGE_NAME:="manylinux${MANYLINUX_VERSION}-${TARGET_ARCH}:${IMAGE_TAG}"}
  CONTAINER_SOURCE=${CONTAINER_SOURCE:="docker.io/dockcross/${MANYLINUX_IMAGE_NAME}"}
elif [[ ${TARGET_ARCH} == aarch64 ]]; then
  MANYLINUX_IMAGE_NAME=${MANYLINUX_IMAGE_NAME:="manylinux${MANYLINUX_VERSION}_${TARGET_ARCH}:${IMAGE_TAG}"}
  CONTAINER_SOURCE=${CONTAINER_SOURCE:="quay.io/pypa/${MANYLINUX_IMAGE_NAME}"}
else
  echo "Unknown target architecture ${TARGET_ARCH}"
  exit 1;
fi

# Configure the oci executable (i.e. docker, containerd, other)
source "${_ipp_dir}/scripts/oci_exe.sh"

mkdir -p ${_ipp_dir}/build


cat > ${BUILD_ENV_REPORT} << DEFAULT_ENV_SETTINGS
################################################
################################################
###  ITKPythonPackage Environment Variables  ###
###  in .env format (KEY=VALUE)              ###

# - "ITK_GIT_TAG": Tag/branch/hash for ITKPythonBuilds build cache to use
#   Which ITK git tag/hash/branch to use as reference for building wheels/modules
#   https://github.com/InsightSoftwareConsortium/ITK.git@\${ITK_GIT_TAG}
#   Examples: "v5.4.0", "v5.2.1.post1" "0ffcaed12552" "my-testing-branch"
#   See available release tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags
ITK_GIT_TAG=${ITK_GIT_TAG:=${_ipp_latest_tag}}

# - "ITK_SOURCE_DIR":  When building different "flavor" of ITK python packages
#   on a given platform, explicitly setting the ITK_SOURCE_DIR options allow to
#   speed up source-code downloads by re-using an existing repository.
#   If the requested directory does not exist, manually clone and checkout ${ITK_GIT_TAG}
ITK_SOURCE_DIR=${ITK_SOURCE_DIR}

#
# - "ITK_PACKAGE_VERSION" A valid versioning formatted tag.  This may be ITK_GIT_TAG for tagged releases
#   Use the keyword 'AUTOVERSION' to have a temporary version automatically created from based on
#   git hash and the checked out ITK_GIT_TAG
#   (in github action ITKRemoteModuleBuildTestPackage itk-wheel-tag is used to set this value)
ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION:=${_ipp_latest_version}}

# - "ITKPYTHONPACKAGE_ORG": Github organization or user to use for ITKPythonPackage build scripts
#   Which script version to use in generating python packages
#   https://github.com/InsightSoftwareConsortium/\${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git@\${ITKPYTHONPACKAGE_TAG}
#   build script source. Default is InsightSoftwareConsortium.
#   Ignored if ITKPYTHONPACKAGE_TAG is empty.
#   (in github action ITKRemoteModuleBuildTestPackage itk-python-package-org is used to set this value)
ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}

# - "ITKPYTHONPACKAGE_TAG": Tag for ITKPythonPackage build scripts to use.
#   If ITKPYTHONPACKAGE_TAG is empty then the default scripts distributed
#   with the ITKPythonBuilds archive will be used.
#   (in github action ITKRemoteModuleBuildTestPackage itk-python-package-tag is used to set this value)
ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG:=${_ipp_latest_tag}}

# - "ITK_MODULE_PREQ": Prerequisite ITK modules that must be built before the requested module.
#   Format is "<org_name>/<module_name>@<module_tag>:<org_name>/<module_name>@<module_tag>:...".
#   For instance, "export ITK_MODULE_PREQ=InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0"
#   See notes in "dockcross-manylinux-build-module-deps.sh".
#   (in github action ITKRemoteModuleBuildTestPackage itk-module-deps is used to set this value)
ITK_MODULE_PREQ=${ITK_MODULE_PREQ:=}

# - "NO_SUDO":
#   Disable if running docker does not require sudo priveleges
#   (set to 1 if your user account can run docker, set to 0 otherwise).
NO_SUDO=${NO_SUDO:=0}

# - "ITK_MODULE_NO_CLEANUP": Option to skip cleanup steps.
#   =1 <- Leave tempoary build files in place after completion, 0 <- remove temporary build files
ITK_MODULE_NO_CLEANUP=${ITK_MODULE_NO_CLEANUP:=1}

# - "USE_CCACHE": Option to indicate that ccache should be used
#   =1 <- Set cmake settings to use ccache for acclerating rebuilds, 0 <- no ccache usage
USE_CCACHE=${USE_CCACHE:=0}

DOXYGEN_EXECUTABLE=${DOXYGEN_EXECUTABLE}
NINJA_EXECUTABLE=${NINJA_EXECUTABLE}
CMAKE_EXECUTABLE=${CMAKE_EXECUTABLE}
DEFAULT_ENV_SETTINGS

if [[ "$(uname)" == "Linux" ]]; then
# Linux uses dockcross containers to perform cross compilations
# for greater compliance across a wide range of linux distributions.
# Inside the containers it is asssumed that each container's default
# compilation envrionment is sufficeintly setup to not require
# setting CXX, CC, CFLAGS, CXXFLAGS etc from the HOST environment.
#
# The choice of container dictates the choice of compiler toolchain.

cat >> ${BUILD_ENV_REPORT} << DEFAULT_LINUX_ENV_SETTINGS
# Which container to use for generating cross compiled packages
OCI_EXE=${OCI_EXE:=$(ociExe)}

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

# Almost never change MANYLINUX_IMAGE_NAME or CONTAINER_SOURCE, keep in sync with 
MANYLINUX_IMAGE_NAME=manylinux\${MANYLINUX_VERSION}_\${TARGET_ARCH}:\${IMAGE_TAG}
CONTAINER_SOURCE=${CONTAINER_SOURCE}

DEFAULT_LINUX_ENV_SETTINGS
fi

if [[ "$(uname)" == "Darwin" ]]; then
# Darwin package builds do not do cross compilation in containers
# There is *only* the HOST environment is used for compilation,
# so ensure the compile influencing environmental variables are
# respected in the scripts.
#
# Setup system dependant compiler options,
# note cmake will respect environmental variables
# CC          – C compiler
# CXX         – C++ compiler
# CUDAHOSTCXX – Host compiler for CUDA
# CFLAGS      – baseline C flags
# CXXFLAGS    – baseline C++ flags
# CPPFLAGS    – preprocessor flags (added to all languages)
# LDFLAGS     – link flags for all languages
# Use cmake to find and set CC and CXX if not previously set
if [ -z "$CC" ]; then
  test -f ${_ipp_dir}/build/cmake_system_information || cmake --system-information > ${_ipp_dir}/build/cmake_system_information 2>&1
  CC_DEFAULT=$(grep "CMAKE_C_COMPILER == "  ${_ipp_dir}/build/cmake_system_information| tr " " "\n" |sed -n "3p")
fi
if [ -z "$CXX" ]; then
  test -f ${_ipp_dir}/build/cmake_system_information || cmake --system-information > ${_ipp_dir}/build/cmake_system_information 2>&1
  CXX_DEFAULT=$(grep "CMAKE_CXX_COMPILER == "  ${_ipp_dir}/build/cmake_system_information| tr " " "\n" |sed -n "3p")
fi


  ################################################
  # when building in host environment

  # Append compiler Vars to persist across shells/tools
  BUILD_VARS=(
    CC
    CXX
    FC
    CFLAGS
    CXXFLAGS
    FFLAGS
    CPPFLAGS
    LDFLAGS
    SDKROOT
    MACOSX_DEPLOYMENT_TARGET
    PKG_CONFIG_PATH
    PKG_CONFIG_LIBDIR
    LD_LIBRARY_PATH
    DYLD_LIBRARY_PATH
    CC_DEFAULT  # used as hint for developer
    CXX_DEFAULT # used as hint for developer
  )

  {
    # - "ITK_USE_LOCAL_PYTHON": For APPLE ONLY Determine how to get Python framework for build.
    #    - If empty, Python frameworks will be fetched from python.org
    #    - If not empty, frameworks already on machine will be used without fetching.
    ITK_USE_LOCAL_PYTHON=${ITK_USE_LOCAL_PYTHON}

    echo "# Standard environmental build flags respected by cmake and other build tools"
    echo "# Autogenerated build environment"
    echo "# Generated: $(date)"
    echo "# Source this file in bash/zsh/python(dot-env) before builds"

    for var in "${BUILD_VARS[@]}"; do
      # Indirect expansion; empty if unset
      value=$(indirect $var)
      if [[ -n "${value}" ]]; then
        # %q produces a shell-escaped representation (bash/zsh)
        printf '%s=%q\n' "${var}" "${value}"
      else
        printf '## - %s=%q\n' "${var}" "${value}"
      fi
    done
  } >> "${BUILD_ENV_REPORT}"
fi
cat ${BUILD_ENV_REPORT}
