#!/bin/bash

########################################################################
# This module should be pulled and run from an ITK external module root directory
# to generate the Mac python wheels of this module.
#
# ========================================================================
# PARAMETERS
#
# Versions can be restricted by passing them in as arguments to the script.
# For example,
#
#   scripts/macpython-build-module-wheels.sh 3.7 3.9
# Shared libraries can be included in the wheel by exporting them to DYLD_LIBRARY_PATH before
# running this script.
#
# ===========================================
# ENVIRONMENT VARIABLES
#
# These variables are set with the `export` bash command before calling the script.
# For example,
#
#   export DYLD_LIBRARY_PATH="/path/to/libs"
#   scripts/macpython-build-module-wheels.sh 3.7 3.9
#
# `ITK_PACKAGE_VERSION`: ITKPythonBuilds archive tag to use for ITK build artifacts.
#   See https://github.com/InsightSoftwareConsortium/ITKPythonBuilds for available tags.
#   For instance, `export ITK_PACKAGE_VERSION=v5.4.0`.
#
# `ITKPYTHONPACKAGE_ORG`: Github organization for fetching ITKPythonPackage build scripts.
#
# `ITKPYTHONPACKAGE_TAG`: ITKPythonPackage tag for fetching build scripts.
#
# `ITK_USE_LOCAL_PYTHON`: Determine how to get Python framework for build.
#    - If empty, Python frameworks will be fetched from python.org
#    - If not empty, frameworks already on machine will be used without fetching.
#
########################################################################

# Install dependencies
brew update
brew install zstd aria2 gnu-tar doxygen ninja
brew upgrade cmake

if [[ $(arch) == "arm64" ]]; then
  tarball_arch="-arm64"
else
  tarball_arch=""
fi
# Fetch ITKPythonBuilds archive containing ITK build artifacts
rm -fr ITKPythonPackage
echo "Fetching https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.4.0}/ITKPythonBuilds-macosx${tarball_arch}.tar.zst"
if [[ ! -f ITKPythonBuilds-macosx${tarball_arch}.tar.zst ]]; then
  aria2c -c --file-allocation=none -o ITKPythonBuilds-macosx${tarball_arch}.tar.zst -s 10 -x 10 https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.4.0}/ITKPythonBuilds-macosx${tarball_arch}.tar.zst
fi
unzstd --long=31 ITKPythonBuilds-macosx${tarball_arch}.tar.zst -o ITKPythonBuilds-macosx${tarball_arch}.tar
PATH="$(dirname $(brew list gnu-tar | grep gnubin)):$PATH"
gtar xf ITKPythonBuilds-macosx${tarball_arch}.tar --checkpoint=10000 --checkpoint-action=dot \
  ITKPythonPackage/ITK-source \
  ITKPythonPackageRequiredExtractionDir.txt \
  ITKPythonPackage/scripts

# Extract subdirectories specific to the compiled python versions
args=( "$@"  )
source ITKPythonPackage/scripts/macpython-build-common.sh
for version in "$PYTHON_VERSIONS"; do
  gtar xf ITKPythonBuilds-macosx${tarball_arch}.tar --checkpoint=10000 --checkpoint-action=dot \
    --wildcards "ITKPythonPackage/ITK-${version}-macosx*" \
    "ITKPythonPackage/venvs/${version}"
done

rm ITKPythonBuilds-macosx${tarball_arch}.tar

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

# Optionally install baseline Python versions
if [[ ! ${ITK_USE_LOCAL_PYTHON} ]]; then
  echo "Fetching Python frameworks"
  sudo rm -rf /Library/Frameworks/Python.framework/Versions/*
  /Users/svc-dashboard/D/P/ITKPythonPackage/scripts/macpython-install-python.sh
fi

echo "Building module wheels"
/Users/svc-dashboard/D/P/ITKPythonPackage/scripts/macpython-build-module-wheels.sh "${args[@]}"
