#!/bin/bash

########################################################################
# Run this script in an ITK external module directory to generate
# build artifacts for prerequisite ITK external modules.
#
# Module dependencies are built in a flat directory structure regardless
# of recursive dependencies. Prerequisite sources are required to be passed
# in the order in which they should be built.
# For example, if ITKTargetModule depends on ITKTargetModuleDep2 which
# depends on ITKTargetModuleDep1, the output directory structure
# will look like this:
#
# / ITKTargetModule
# -- / ITKTargetModuleDep1
# -- / ITKTargetModuleDep2
# ..
#
# ===========================================
# ENVIRONMENT VARIABLES: ITK_MODULE_PREQ
#
########################################################################

# Initialize variables

script_dir=$(cd $(dirname $0) || exit 1; pwd)
_ipp_dir=$(dirname ${script_dir})
package_env_file=${_ipp_dir}/build/package.env
if [ ! -f "${package_env_file}" ]; then
  ${_ipp_dir}/generate_build_environment.sh -o ${package_env_file}
fi
source "${package_env_file}"

if [[ ! -f "${script_dir}/dockcross-manylinux-download-cache-and-build-module-wheels.sh" ]]; then
  echo "Could not find download script to use for building module dependencies!"
  exit 1
fi

# Temporarily update prerequisite environment variable to prevent infinite recursion.
ITK_MODULE_PREQ_TOPLEVEL=${ITK_MODULE_PREQ}
ITK_MODULE_NO_CLEANUP_TOPLEVEL=${ITK_MODULE_NO_CLEANUP}
export ITK_MODULE_PREQ=""
export ITK_MODULE_NO_CLEANUP="ON"

########################################################################
# Build ITK module dependencies

for MODULE_INFO in ${ITK_MODULE_PREQ_TOPLEVEL//:/ }; do
  MODULE_ORG=`(echo ${MODULE_INFO} | cut -d'/' -f 1)`
  MODULE_NAME=`(echo ${MODULE_INFO} | cut -d'@' -f 1 | cut -d'/' -f 2)`
  MODULE_TAG=`(echo ${MODULE_INFO} | cut -d'@' -f 2)`

  MODULE_UPSTREAM=https://github.com/${MODULE_ORG}/${MODULE_NAME}.git
  echo "Cloning from ${MODULE_UPSTREAM}"
  git clone ${MODULE_UPSTREAM}

  # Reuse cached build archive instead of redownloading.
  # Build archives are usually ~2GB so it is reasonable to move
  # instead of redownloading.
  if [[ `(compgen -G ./ITKPythonBuilds-linux*.tar.zst)` ]]; then
    mv ITKPythonBuilds-linux*.tar.zst ${MODULE_NAME}/
  fi

  pushd ${MODULE_NAME}
  git checkout ${MODULE_TAG}
  cp ../dockcross-manylinux-download-cache-and-build-module-wheels.sh .
  if [[ -d ../ITKPythonPackage ]]; then
    ln -s ../ITKPythonPackage
    ln -s ./ITKPythonPackage/oneTBB-prefix
  fi

  echo "Building module dependency ${MODULE_NAME}"
  ./dockcross-manylinux-download-cache-and-build-module-wheels.sh "$@"
  popd

  echo "Cleaning up module dependency"
  cp ./${MODULE_NAME}/include/* include/
  find ${MODULE_NAME}/wrapping -name '*.in' -print -exec cp {} wrapping \;
  find ${MODULE_NAME}/wrapping -name '*.init' -print -exec cp {} wrapping \;
  find ${MODULE_NAME}/*build/*/include -type f -print -exec cp {} include \;

  # Cache build archive
  if [[ `(compgen -G ./ITKPythonBuilds-linux*.tar.zst)` ]]; then
    rm -f ./${MODULE_NAME}/ITKPythonBuilds-linux*.tar.zst
  else
    mv ./${MODULE_NAME}/ITKPythonBuilds-linux*.tar.zst .
  fi

  # Cache ITKPythonPackage build scripts
  if [[ ! -d ./ITKPythonPackage ]]; then
    mv ./${MODULE_NAME}/ITKPythonPackage .
    ln -s ./ITKPythonPackage/oneTBB-prefix .
  fi

done

# Restore environment variable
export ITK_MODULE_PREQ=${ITK_MODULE_PREQ_TOPLEVEL}
ITK_MODULE_PREQ_TOPLEVEL=""
export ITK_MODULE_NO_CLEANUP=${ITK_MODULE_NO_CLEANUP_TOPLEVEL}
ITK_MODULE_NO_CLEANUP_TOPLEVEL=""

# Summarize disk usage for debugging
du -sh ./* | sort -hr | head -n 20

echo "Done building ITK external module dependencies"
