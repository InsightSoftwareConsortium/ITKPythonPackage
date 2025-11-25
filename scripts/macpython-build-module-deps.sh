#!/bin/bash

########################################################################
# Run this script in an ITK external module directory to generate
# build artifacts for prerequisite ITK MacOS modules.
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
# ENVIRONMENT VARIABLES
########################################################################

if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    echo "ERROR: This script must be sourced with _ipp_dir predefined, not executed as a script."
    exit 1
fi

if [[ ! -f "${script_dir}/macpython-download-cache-and-build-module-wheels.sh" ]]; then
  echo "Could not find download script to use for building module dependencies!"
  exit 1
fi

# Temporarily update prerequisite environment variable to prevent infinite recursion.
ITK_MODULE_PREQ_TOPLEVEL=${ITK_MODULE_PREQ}
ITK_USE_LOCAL_PYTHON_TOPLEVEL=${ITK_USE_LOCAL_PYTHON}

# Temporary values within script (to be resored at end of the script).
export ITK_MODULE_PREQ=""
export ITK_USE_LOCAL_PYTHON="ON"

########################################################################
echo "Building ITK module dependencies: ${ITK_MODULE_PREQ_TOPLEVEL}"

for MODULE_INFO in ${ITK_MODULE_PREQ_TOPLEVEL//:/ }; do
  MODULE_ORG=`(echo ${MODULE_INFO} | cut -d'/' -f 1)`
  MODULE_NAME=`(echo ${MODULE_INFO} | cut -d'@' -f 1 | cut -d'/' -f 2)`
  MODULE_TAG=`(echo ${MODULE_INFO} | cut -d'@' -f 2)`

  MODULE_UPSTREAM=https://github.com/${MODULE_ORG}/${MODULE_NAME}.git
  echo "Cloning from ${MODULE_UPSTREAM}"
  git clone ${MODULE_UPSTREAM}

  pushd ${MODULE_NAME}
  git checkout ${MODULE_TAG}
  cp ${script_dir}/macpython-download-cache-and-build-module-wheels.sh .
  echo "Building dependency ${MODULE_NAME}"
  ./macpython-download-cache-and-build-module-wheels.sh $@
  popd

  cp ./${MODULE_NAME}/include/* include/
  find ${MODULE_NAME}/wrapping -name '*.in' -print -exec cp {} wrapping \;
  find ${MODULE_NAME}/wrapping -name '*.init' -print -exec cp {} wrapping \;
  find ${MODULE_NAME}/*build/*/include -type f -print -exec cp {} include \;
  rm -f ./${MODULE_NAME}/ITKPythonBuilds-macosx.tar.zst
done

# Restore environment variable
export ITK_MODULE_PREQ=${ITK_MODULE_PREQ_TOPLEVEL}
export ITK_USE_LOCAL_PYTHON=${ITK_USE_LOCAL_PYTHON_TOPLEVEL}
ITK_MODULE_PREQ_TOPLEVEL=""
ITK_USE_LOCAL_PYTHON_TOPLEVEL=""

# Summarize disk usage for debugging
du -sh ./* | sort -hr | head -n 20

echo "Done building ITK external module dependencies"
