#!/usr/bin/env bash

# This script creates a tarball of the ITK Python package build tree. It is
# downloaded by the external module build scripts and used to build their
# Python package on GitHub CI services.

#tbb_contents="ITKPythonPackage/oneTBB*"
tbb_contents=""
arch_postfix=""
if test $(arch) == "arm64"; then
  arch_postfix="-arm64"
  tbb_contents=""
fi

pushd /Users/svc-dashboard/D/P > /dev/null
tar -cf ITKPythonBuilds-macosx${arch_postfix}.tar \
  ITKPythonPackage/ITK-* \
  ${tbb_contents} \
  ITKPythonPackage/venvs \
  ITKPythonPackageRequiredExtractionDir.txt \
  ITKPythonPackage/scripts
zstd -f \
  -10 \
  -T6 \
  --long=31 \
  ./ITKPythonBuilds-macosx${arch_postfix}.tar \
  -o ./ITKPythonBuilds-macosx${arch_postfix}.tar.zst
popd > /dev/null
