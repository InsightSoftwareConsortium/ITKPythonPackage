#!/bin/bash

# This module should be pull and run from an ITKModule root directory to generate the Mac python wheels of this module,
# it is used by the .travis.yml file contained in ITKModuleTemplate: https://github.com/InsightSoftwareConsortium/ITKModuleTemplate

brew update
brew install zstd aria2 gnu-tar doxygen
brew upgrade cmake
aria2c -c --file-allocation=none -o ITKPythonBuilds-macosx.tar.zst -s 10 -x 10 https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.2.0.post1}/ITKPythonBuilds-macosx.tar.zst
unzstd ITKPythonBuilds-macosx.tar.zst -o ITKPythonBuilds-macosx.tar
PATH="/usr/local/opt/gnu-tar/libexec/gnubin:$PATH"
tar xf ITKPythonBuilds-macosx.tar --checkpoint=10000 --checkpoint-action=dot
rm ITKPythonBuilds-macosx.tar
sudo mkdir -p /Users/svc-dashboard/D/P && sudo chown $UID:$GID /Users/svc-dashboard/D/P && mv ITKPythonPackage /Users/svc-dashboard/D/P/
sudo rm -rf /Library/Frameworks/Python.framework/Versions/*
/Users/svc-dashboard/D/P/ITKPythonPackage/scripts/macpython-install-python.sh
/Users/svc-dashboard/D/P/ITKPythonPackage/scripts/macpython-build-module-wheels.sh "$@"
