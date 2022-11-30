#!/bin/bash

# This module should be pull and run from an ITKModule root directory to generate the Mac python wheels of this module,
# it is used by the .travis.yml file contained in ITKModuleTemplate: https://github.com/InsightSoftwareConsortium/ITKModuleTemplate
# 
# Exported variables used in this script:
# - ITK_PACKAGE_VERSION: Tag for ITKPythonBuilds build archive to use
# - ITKPYTHONPACKAGE_TAG: Tag for ITKPythonPackage build scripts to use.
#     If ITKPYTHONPACKAGE_TAG is empty then the default scripts distributed
#     with the ITKPythonBuilds archive will be used.
# - ITKPYTHONPACKAGE_ORG: Github organization or user to use for ITKPythonPackage
#     build script source. Default is InsightSoftwareConsortium.
#     Ignored if ITKPYTHONPACKAGE_TAG is empty.

# Install dependencies
brew update
brew install zstd aria2 gnu-tar doxygen ninja
brew upgrade cmake

# Fetch ITKPythonBuilds archive containing ITK build artifacts
aria2c -c --file-allocation=none -o ITKPythonBuilds-macosx.tar.zst -s 10 -x 10 https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.3.0}/ITKPythonBuilds-macosx.tar.zst
unzstd --long=31 ITKPythonBuilds-macosx.tar.zst -o ITKPythonBuilds-macosx.tar
PATH="/usr/local/opt/gnu-tar/libexec/gnubin:$PATH"
tar xf ITKPythonBuilds-macosx.tar --checkpoint=10000 --checkpoint-action=dot
rm ITKPythonBuilds-macosx.tar

# Optional: Update build scripts
if [[ -n ${ITKPYTHONPACKAGE_TAG} ]]; then
  echo "Updating build scripts to ${ITKPYTHONPACKAGE_ORG:=InsightSoftwareConsortium}/ITKPythonPackage@${ITKPYTHONPACKAGE_TAG}"
  git clone "https://github.com/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git" "IPP-tmp"
  pushd IPP-tmp/
  git checkout "${ITKPYTHONPACKAGE_TAG}"
  git status
  popd
  
  rm -rf ITKPythonPackage/scripts/
  cp -r IPP-tmp/scripts ITKPythonPackage/
  rm -rf IPP-tmp/
fi

# Run build scripts
sudo mkdir -p /Users/svc-dashboard/D/P && sudo chown $UID:$GID /Users/svc-dashboard/D/P && mv ITKPythonPackage /Users/svc-dashboard/D/P/
sudo rm -rf /Library/Frameworks/Python.framework/Versions/*
/Users/svc-dashboard/D/P/ITKPythonPackage/scripts/macpython-install-python.sh
/Users/svc-dashboard/D/P/ITKPythonPackage/scripts/macpython-build-module-wheels.sh "$@"
