#!/bin/bash

# This module should be pull and run from an ITKModule root directory to generate the Mac python wheels of this module,
# it is used by the .travis.yml file contained in ITKModuleTemplate: https://github.com/InsightSoftwareConsortium/ITKModuleTemplate

wget -L https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/v4.12.0.post1/ITKPythonBuilds-macosx.tar.zst -O ITKPythonBuilds-macosx.tar.zst --retry-connrefused --waitretry=1
brew install zstd
unzstd ITKPythonBuilds-macosx.tar.zst -o ITKPythonBuilds-macosx.tar
brew install gnu-tar
PATH="/usr/local/opt/gnu-tar/libexec/gnubin:$PATH"
tar xf ITKPythonBuilds-macosx.tar --checkpoint=10000 --checkpoint-action=dot
sudo mkdir -p /Users/Kitware/Dashboards/ITK && sudo chown $UID:$GID /Users/Kitware/Dashboards/ITK && mv ITKPythonPackage /Users/Kitware/Dashboards/ITK/
/Users/Kitware/Dashboards/ITK/ITKPythonPackage/scripts/macpython-install-python.sh
/Users/Kitware/Dashboards/ITK/ITKPythonPackage/scripts/macpython-build-module-wheels.sh
