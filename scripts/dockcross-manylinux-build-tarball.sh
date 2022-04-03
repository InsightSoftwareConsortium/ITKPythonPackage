#!/usr/bin/env bash

# This script creates a tarball of the ITK Python package build tree. It is
# downloaded by the external module build scripts and used to build their
# Python package on GitHub CI services.

if test -d /home/kitware/Packaging; then
  cd /home/kitware/Packaging
fi
zstd_exe=zstd
if test -e /home/kitware/Support/zstd-build/programs/zstd; then
  zstd_exe=/home/kitware/Support/zstd-build/programs/zstd
fi
tar -c --to-stdout \
  ITKPythonPackage/ITK-* \
  ITKPythonPackage/oneTBB* \
  ITKPythonPackage/scripts > ITKPythonBuilds-linux.tar
$zstd_exe -f \
  -10 \
  -T6 \
  --long=31 \
  ./ITKPythonBuilds-linux.tar \
  -o ./ITKPythonBuilds-linux.tar.zst
