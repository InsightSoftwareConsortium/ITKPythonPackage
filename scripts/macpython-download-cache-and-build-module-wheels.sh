#!/bin/bash

# This module should be pull and run from an ITKModule root directory to generate the Mac python wheels of this module,
# it is used by the .travis.yml file contained in ITKModuleTemplate: https://github.com/InsightSoftwareConsortium/ITKModuleTemplate

brew update
brew install zstd aria2 gnu-tar doxygen
brew upgrade cmake
# The Azure systems current do not have the 10.13 SDK, required by the
# ITKPythonBuilds
SDK_PATH='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.13.sdk'
if test ! -e $SDK_PATH; then
  sudo ln -s /Applications/Xcode_9.4.1.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.13.sdk /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.13.sdk
fi
aria2c -c --file-allocation=none -o ITKPythonBuilds-macosx.tar.zst -s 10 -x 10 https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.0rc02}/ITKPythonBuilds-macosx.tar.zst
unzstd ITKPythonBuilds-macosx.tar.zst -o ITKPythonBuilds-macosx.tar
PATH="/usr/local/opt/gnu-tar/libexec/gnubin:$PATH"
tar xf ITKPythonBuilds-macosx.tar --checkpoint=10000 --checkpoint-action=dot
sudo mkdir -p /Users/Kitware/Dashboards/ITK && sudo chown $UID:$GID /Users/Kitware/Dashboards/ITK && mv ITKPythonPackage /Users/Kitware/Dashboards/ITK/
/Users/Kitware/Dashboards/ITK/ITKPythonPackage/scripts/macpython-install-python.sh
/Users/Kitware/Dashboards/ITK/ITKPythonPackage/scripts/macpython-build-module-wheels.sh "$@"
