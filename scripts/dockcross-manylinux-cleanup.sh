#!/bin/bash

########################################################################
# Run this script in an ITK external module directory to clean up
# Linux Python build artifacts.
#
# Typically required for building multiple types of module wheels in the same
# directory, such as using different toolsets or targeting different
# architectures.
#
# ===========================================
# ENVIRONMENT VARIABLES
#
# - `ITK_MODULE_PREQ`: Prerequisite ITK modules that must be built before the requested module.
#   Format is `<org_name>/<module_name>@<module_tag>:<org_name>/<module_name>@<module_tag>:...`.
#   For instance, `export ITK_MODULE_PREQ=InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0`
#
# - `NO_SUDO`: Disable the use of superuser permissions for removing directories.
#    `sudo` is required by default for cleanup on Github Actions runners.
#
########################################################################

echo "Cleaning up artifacts from module build"

# ARM platform observed to require sudo for removing ITKPythonPackage sources
rm_prefix=""
if [[ ! ${NO_SUDO} ]]; then
  rm_prefix="sudo "
fi

unlink oneTBB-prefix
${rm_prefix} rm -rf ITKPythonPackage/
${rm_prefix} rm -rf tools/
${rm_prefix} rm -rf _skbuild/ build/
${rm_prefix} rm -rf ./*.egg-info/
${rm_prefix} rm -rf ./ITK-*-manylinux${MANYLINUX_VERSION}_${TARGET_ARCH}/
${rm_prefix} rm -rf ./ITKPythonBuilds-linux-manylinux*${MANYLINUX_VERSION}*.tar.zst

if [[ -n ${ITK_MODULE_PREQ} ]]; then
  for MODULE_INFO in ${ITK_MODULE_PREQ//:/ }; do
    MODULE_NAME=`(echo ${MODULE_INFO} | cut -d'@' -f 1 | cut -d'/' -f 2)`
    ${rm_prefix} rm -rf ${MODULE_NAME}/
  done
fi

# Leave dist/ and download scripts intact
