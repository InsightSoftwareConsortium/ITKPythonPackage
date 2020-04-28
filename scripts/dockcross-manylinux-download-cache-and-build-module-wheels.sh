#!/bin/bash

# This module should be pulled and run from an ITKModule root directory to generate the Linux python wheels of this module,
# it is used by the azure-pipeline.yml file contained in ITKModuleTemplate: https://github.com/InsightSoftwareConsortium/ITKModuleTemplate
# First download doxygen
if [[ ! -f doxygen-1.8.11.linux.bin.tar.gz ]]; then
  mkdir tools
  curl https://data.kitware.com/api/v1/file/5c0aa4b18d777f2179dd0a71/download -o doxygen-1.8.11.linux.bin.tar.gz
  tar -xvzf doxygen-1.8.11.linux.bin.tar.gz -C tools
fi
if [[ ! -f ./tools/doxygen-1.8.11/bin/doxygen ]]; then
  echo "ERROR: can not find required binary './tools/doxygen-1.8.11/bin/doxygen'"
  exit 255
fi

# Packages distributed by github are in zstd format, so we need to download that binary to uncompress
if [[ ! -f zstd-1.2.0-linux.tar.gz ]]; then
  curl https://data.kitware.com/api/v1/file/592dd8068d777f16d01e1a92/download -o zstd-1.2.0-linux.tar.gz
  gunzip -d zstd-1.2.0-linux.tar.gz
  tar xf zstd-1.2.0-linux.tar
fi
if [[ ! -f ./zstd-1.2.0-linux/bin/unzstd ]]; then
  echo "ERROR: can not find required binary './zstd-1.2.0-linux/bin/unzstd'"
  exit 255
fi

if [[ ! -f ITKPythonBuilds-linux.tar.zst ]]; then
  curl -L https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/releases/download/${ITK_PACKAGE_VERSION:=v5.1rc02}/ITKPythonBuilds-linux.tar.zst -O
fi
if [[ ! -f ./ITKPythonBuilds-linux.tar.zst ]]; then
  echo "ERROR: can not find required binary './ITKPythonBuilds-linux.tar.zst'"
  exit 255
fi
./zstd-1.2.0-linux/bin/unzstd ./ITKPythonBuilds-linux.tar.zst -o ITKPythonBuilds-linux.tar
tar xf ITKPythonBuilds-linux.tar
rm ITKPythonBuilds-linux.tar
if [[ ! -f ./ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh ]]; then
  echo "ERROR: can not find required binary './ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh'"
  exit 255
fi

./ITKPythonPackage/scripts/dockcross-manylinux-build-module-wheels.sh "$@"
