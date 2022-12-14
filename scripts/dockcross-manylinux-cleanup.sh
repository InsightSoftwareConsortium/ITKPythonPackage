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
########################################################################

echo "Cleaning up module dependencies"
unlink oneTBB-prefix
rm -rf ITKPythonPackage/

if [[ -n ${ITK_MODULE_PREQ} ]]; then
  for MODULE_INFO in ${ITK_MODULE_PREQ//:/ }; do
    MODULE_NAME=`(echo ${MODULE_INFO} | cut -d'@' -f 1 | cut -d'/' -f 2)`
    sudo rm -rf ${MODULE_NAME}/
  done
fi
