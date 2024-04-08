#!/usr/bin/env bash

# Run this script inside a dockcross container to build Python wheels for an aarch ITK module.
cd /work
yum -y install sudo ninja-build
/opt/python/cp39-cp39/bin/python -m pip install -r /ITKPythonPackage/requirements-dev.txt
for PYBIN in "${PYBINARIES[@]}"; do
  ${PYBIN}/pip install -r /ITKPythonPackage/requirements-dev.txt
done

"/ITKPythonPackage/scripts/internal/manylinux-build-module-wheels.sh" "$@"
