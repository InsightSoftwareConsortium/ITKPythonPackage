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
#   scripts/macpython-download-cache-and-build-module-wheels.sh 3.9 3.11
#
# Shared libraries can be included in the wheel by setting DYLD_LIBRARY_PATH before
# running this script.
#
# ===========================================
# ENVIRONMENT VARIABLES: ITK_GIT_TAG ITKPYTHONPACKAGE_ORG ITK_USE_LOCAL_PYTHON
#
# These variables are set with the `export` bash command before calling the script.
# For example,
#
#   generate_build_environment.sh # creates default build/package.env
#   edit build/package.env with desired build elements
#   scripts/macpython-build-module-wheels.sh 3.7 3.9
#
########################################################################

# Install dependencies
brew update
brew install --quiet zstd aria2 gnu-tar doxygen ninja
#
# As discussed in issue #282, rustup is not needed for successful packaging
# but brew eco-system will warn verbosely about it being out of date which
# makes identifying other errors more difficult. upgrading rustup silences
# the warnings unrelated to package building for easing developer reviews.
brew upgrade --quiet cmake rustup

if [[ $(arch) == "arm64" ]]; then
  tarball_arch="-arm64"
else
  tarball_arch=""
fi
# Fetch ITKPythonBuilds archive containing ITK build artifacts
rm -fr ITKPythonPackage
echo "Fetching https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION}/ITKPythonBuilds-macosx${tarball_arch}.tar.zst"
if [[ ! -f ITKPythonBuilds-macosx${tarball_arch}.tar.zst ]]; then
  aria2c -c --file-allocation=none -o ITKPythonBuilds-macosx${tarball_arch}.tar.zst -s 10 -x 10 https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION}/ITKPythonBuilds-macosx${tarball_arch}.tar.zst
fi
unzstd --long=31 ITKPythonBuilds-macosx${tarball_arch}.tar.zst -o ITKPythonBuilds-macosx${tarball_arch}.tar
PATH="$(dirname $(brew list gnu-tar | grep gnubin)):$PATH"
gtar xf ITKPythonBuilds-macosx${tarball_arch}.tar --warning=no-unknown-keyword --checkpoint=10000 --checkpoint-action=dot \
  ITKPythonPackage/ITK-source \
  ITKPythonPackageRequiredExtractionDir.txt \
  ITKPythonPackage/scripts

# Extract subdirectories specific to the compiled python versions
args=( "$@"  )
source ITKPythonPackage/scripts/macpython-build-common.sh
for version in "$PYTHON_VERSIONS"; do
  gtar xf ITKPythonBuilds-macosx${tarball_arch}.tar --warning=no-unknown-keyword --checkpoint=10000 --checkpoint-action=dot \
    --wildcards "ITKPythonPackage/ITK-${version}-macosx*" \
    "ITKPythonPackage/venvs/${version}"
done

rm ITKPythonBuilds-macosx${tarball_arch}.tar

# Optional: Update build scripts
if [[ -n ${ITKPYTHONPACKAGE_TAG} ]]; then
  echo "Updating build scripts to ${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage@${ITKPYTHONPACKAGE_TAG}"
  git clone "https://github.com/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git" "IPP-tmp"
  pushd IPP-tmp/
    git checkout "${ITKPYTHONPACKAGE_TAG}"
    git status
  popd
  # Graft the newly cloned files over the untarred files
  rm -rf ITKPythonPackage/scripts/
  cp -r IPP-tmp/scripts ITKPythonPackage/
  rm -rf IPP-tmp/
fi

DASHBOARD_BUILD_DIRECTORY=/Users/svc-dashboard/D/P
# Run build scripts
sudo mkdir -p ${DASHBOARD_BUILD_DIRECTORY} && sudo chown $UID:$GID ${DASHBOARD_BUILD_DIRECTORY}
if [[ ! -d ${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage ]]; then
  mv ITKPythonPackage ${DASHBOARD_BUILD_DIRECTORY}/
fi

# Optionally install baseline Python versions
if [[ ! ${ITK_USE_LOCAL_PYTHON} ]]; then
  echo "Fetching Python frameworks"
  sudo rm -rf /Library/Frameworks/Python.framework/Versions/*
  ${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage/scripts/macpython-install-python.sh
fi

echo "Building module wheels"
${DASHBOARD_BUILD_DIRECTORY}/ITKPythonPackage/scripts/macpython-build-module-wheels.sh "${args[@]}"
