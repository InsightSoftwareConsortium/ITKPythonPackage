#!/bin/bash
set -e -x

# i686 or x86_64 ?
case $(uname -p) in
    i686)
        arch=x86
        ;;
    x86_64)
        arch=x64
        ;;
    *)
        die "Unknown architecture $(uname -p)"
        ;;
esac

echo "Building wheels for $arch"

# Build standalone project and populate archive cache
mkdir -p /work/standalone-${arch}-build
pushd /work/standalone-${arch}-build > /dev/null 2>&1
  cmake -DITKPythonPackage_BUILD_PYTHON:PATH=0 -G Ninja ../
  ninja
popd > /dev/null 2>&1

# Since the python interpreter exports its symbol (see [1]), python
# modules should not link against any python libraries.
# To ensure it is not the case, we configure the project using an empty
# file as python library.
#
# [1] "Note that libpythonX.Y.so.1 is not on the list of libraries that
# a manylinux1 extension is allowed to link to. Explicitly linking to
# libpythonX.Y.so.1 is unnecessary in almost all cases: the way ELF linking
# works, extension modules that are loaded into the interpreter automatically
# get access to all of the interpreter's symbols, regardless of whether or
# not the extension itself is explicitly linked against libpython. [...]"
#
# Source: https://www.python.org/dev/peps/pep-0513/#libpythonx-y-so-1
PYTHON_LIBRARY=/work/scripts/internal/manylinux-libpython-not-needed-symbols-exported-by-interpreter
touch ${PYTHON_LIBRARY}

# Compile wheels re-using standalone project and archive cache
for PYBIN in /opt/python/*/bin; do
    if [[ ${PYBIN} == *"cp26"* ]]; then
        echo "Skipping ${PYBIN}"
        continue
    fi

    PYTHON_EXECUTABLE=${PYBIN}/python
    PYTHON_INCLUDE_DIR=$( find -L ${PYBIN}/../include/ -name Python.h -exec dirname {} \; )

    echo ""
    echo "PYTHON_EXECUTABLE:${PYTHON_EXECUTABLE}"
    echo "PYTHON_INCLUDE_DIR:${PYTHON_INCLUDE_DIR}"
    echo "PYTHON_LIBRARY:${PYTHON_LIBRARY}"

    ${PYBIN}/pip install -r /work/requirements-dev.txt
    ${PYBIN}/python setup.py bdist_wheel -G Ninja -- \
      -DITK_SOURCE_DIR:PATH=/work/standalone-${arch}-build/ITK-source \
      -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE} \
      -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR} \
      -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY}
    ${PYBIN}/python setup.py clean
done

# Since there are no external shared libraries to bundle into the wheels
# this step will fixup the wheel switching from 'linux' to 'manylinux1' tag
for whl in dist/*$(uname -p).whl; do
    auditwheel repair $whl -w /work/dist/
    rm $whl
done

# Install packages and test
for PYBIN in /opt/python/*/bin/; do
    if [[ ${PYBIN} == *"cp26"* ]]; then
        echo "Skipping ${PYBIN}"
        continue
    fi
    ${PYBIN}/pip install ITK --user --no-cache-dir --no-index -f /work/dist
    (cd $HOME; ${PYBIN}/python -c 'import itk;')
done
