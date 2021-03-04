#!/usr/bin/env bash

# This script creates a tarball of the ITK Python package build tree. It is
# downloaded by the external module build scripts and used to build their
# Python package on GitHub CI services.

pushd /Users/svc-dashboard/D/P > /dev/null
tar -cf ITKPythonBuilds-macosx.tar \
  ITKPythonPackage/ITK-* \
  ITKPythonPackage/venvs \
  ITKPythonPackageRequiredExtractionDir.txt \
  ITKPythonPackage/scripts
/usr/local/bin/zstd -f \
  -15 \
  ./ITKPythonBuilds-macosx.tar \
  -o ./ITKPythonBuilds-macosx.tar.zst
popd > /dev/null
