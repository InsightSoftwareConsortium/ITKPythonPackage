#!/usr/bin/env bash

# This script creates a tarball of the ITK Python package build tree. It is
# downloaded by the external module build scripts and used to build their
# Python package on GitHub CI services.

if test -d /home/kitware/Packaging; then
  cd /home/kitware/Packaging
fi

# -----------------------------------------------------------------------

zstd_exe=`(which zstd)`
if [[ -z ${zstd_exe} && -e /home/kitware/Support/zstd-build/programs/zstd ]]; then
  zstd_exe=/home/kitware/Support/zstd-build/programs/zstd
fi

# Find an appropriately versioned zstd.
#
# "--long" is introduced in zstd==v1.3.2
# https://github.com/facebook/zstd/releases/tag/v1.3.2
#
# Sample --version output:
# *** zstd command line interface 64-bits v1.4.4, by Yann Collet *** #
ZSTD_MIN_VERSION="1.3.2"

if [[ -n `(which dpkg)` && `(${zstd_exe} --version)` =~ v([0-9]+.[0-9]+.[0-9]+) ]]; then
  if $(dpkg --compare-versions ${BASH_REMATCH[1]} "ge" ${ZSTD_MIN_VERSION} ); then
    echo "Found zstd v${BASH_REMATCH[1]} at ${zstd_exe}"
  else
    echo "Expected zstd v${ZSTD_MIN_VERSION} or higher but found v${BASH_REMATCH[1]} at ${zstd_exe}"
    exit 255
  fi
else
  # dpkg not available for version comparison so simply print version
  ${zstd_exe} --version
fi

# -----------------------------------------------------------------------

tar -cf ITKPythonBuilds-linux.tar \
  ITKPythonPackage/ITK-* \
  ITKPythonPackage/oneTBB* \
  ITKPythonPackage/requirements-dev.txt \
  ITKPythonPackage/scripts
$zstd_exe -f \
  -10 \
  -T6 \
  --long=31 \
  ./ITKPythonBuilds-linux.tar \
  -o ./ITKPythonBuilds-linux.tar.zst
