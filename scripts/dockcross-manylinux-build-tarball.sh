#!/usr/bin/env bash

# This script creates a tarball of the ITK Python package build tree. It is
# downloaded by the external module build scripts and used to build their
# Python package on GitHub CI services.

cd /home/kitware/Packaging
tar -c --to-stdout \
  ITKPythonPackage/ITK-* \
  ITKPythonPackage/scripts > ITKPythonBuilds-linux.tar
/home/kitware/Support/zstd-build/programs/zstd -f \
  ./ITKPythonBuilds-linux.tar \
  -o ./ITKPythonBuilds-linux.tar.zst
